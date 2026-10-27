"""Download historical ERA5 *via Open-Meteo*, without using the CDS job queue.

The API is point-based, so query every ERA5 0.25-degree grid node within the
scenario ROI in bounded sequential batches. `cell_selection=nearest` and
`elevation=nan` suppress Open-Meteo's normal land/elevation downscaling. Verify
returned grid coordinates, timestamps, units, and data before converting into
an ERA5-compatible NetCDF consumed by the unchanged StratoQ attenuation engine.

Open-Meteo snowfall [cm] is converted to water equivalent [m] via the documented
7 cm snowfall = 10 mm water-equivalent relation. This processed field is not
byte-identical to a direct CDS ERA5 sf download; see OPEN-METEO-V103.md.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
import gzip
import hashlib
import json
import logging
import math
import os
import time
import traceback
import uuid

import numpy as np

from .era5_weather import CACHE_DIR, _date, register_bytes, roi_from_scenario

LOG = logging.getLogger('uvicorn.error')
ENDPOINT = 'https://archive-api.open-meteo.com/v1/archive'
VARIABLES = ('temperature_2m', 'dew_point_2m', 'precipitation', 'snowfall', 'cloud_cover_low')
UNITS = {'temperature_2m': '°C', 'dew_point_2m': '°C', 'precipitation': 'mm',
         'snowfall': 'cm', 'cloud_cover_low': '%'}
BATCH_SIZE = 20  # modest requests; never more than one in flight per FastAPI server
PARTS_DIR = CACHE_DIR / 'open_meteo_parts'
JOBS_DIR = CACHE_DIR / 'open_meteo_jobs'
_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='open-meteo-fetch')
_LOCK = RLock()
_JOBS: dict[str, dict] = {}


class ERA5BusyError(RuntimeError):
    """Another local weather download is running. HTTP 409."""


def _persist(job):
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    out = JOBS_DIR / f'{job["id"]}.json'
    temp = out.with_name(out.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(job, default=str))
        os.replace(temp, out)
    finally:
        temp.unlink(missing_ok=True)


def _set(jid, **changes):
    with _LOCK:
        job = _JOBS[jid]
        job.update(changes)
        job['updated_at'] = datetime.now(timezone.utc).isoformat()
        _persist(job)


def _axis(lo, hi):
    """Grid-aligned inclusive 0.25° nodes, with no extrapolated values."""
    start, stop = round(lo * 4), round(hi * 4)
    if stop <= start:
        raise ValueError('ERA5 ROI must cover at least two grid nodes on each axis')
    return np.arange(start, stop + 1, dtype=np.int32) / 4.0


def _grid_points(roi):
    n, w, s, e = map(float, roi)
    lats, lons = _axis(s, n), _axis(w, e)
    locations = [(i, j, float(lat), float(lon))
                 for i, lat in enumerate(lats) for j, lon in enumerate(lons)]
    return lats, lons, locations


def _params(day, locations):
    coords = [(lat, lon) for _, _, lat, lon in locations]
    return {
        'latitude': ','.join(str(lat) for lat, _ in coords),
        'longitude': ','.join(str(lon) for _, lon in coords),
        'start_date': day.isoformat(),
        'end_date': (day + timedelta(days=1)).isoformat(),
        'hourly': ','.join(VARIABLES),
        'models': 'era5',
        'timezone': 'GMT',
        'cell_selection': 'nearest',
        'elevation': ','.join(['nan'] * len(coords)),
    }


def _validate_batch(reply, locations, day):
    """Validate both complete days, returning the first 25 hourly samples."""
    if isinstance(reply, dict):
        replies = [reply]
    elif isinstance(reply, list):
        replies = reply
    else:
        raise ValueError('Open-Meteo returned neither an object nor a location list')
    if len(replies) != len(locations):
        raise ValueError(f'Open-Meteo returned {len(replies)} locations for {len(locations)} requested')
    expected = [(datetime.combine(day, datetime.min.time()) + timedelta(hours=h)).strftime('%Y-%m-%dT%H:%M')
                for h in range(25)]
    validated = []
    for (i, j, lat, lon), item in zip(locations, replies):
        if not isinstance(item, dict) or item.get('error'):
            raise ValueError(f'Open-Meteo error: {item.get("reason", item) if isinstance(item, dict) else item}')
        # A neighboring ERA5 grid point (or a downscaled location) must not be
        # mislabeled as our requested native grid cell.
        if abs(float(item['latitude'])-lat) > 0.025 or abs(float(item['longitude'])-lon) > 0.025:
            raise ValueError(f'Open-Meteo snapped ({lat},{lon}) to '
                             f'({item["latitude"]},{item["longitude"]}); cannot construct faithful grid')
        if item.get('utc_offset_seconds') != 0:
            raise ValueError('Expected UTC (GMT) weather timestamps')
        hourly = item.get('hourly') or {}
        times = hourly.get('time') or []
        if times[:25] != expected or len(times) != 48:
            raise ValueError(f'Open-Meteo timestamps differ from the 48 expected hours for {day}')
        actual_units = item.get('hourly_units') or {}
        converted = {}
        for var in VARIABLES:
            if actual_units.get(var) != UNITS[var]:
                raise ValueError(f'Unexpected Open-Meteo unit for {var}: {actual_units.get(var)!r}')
            values = hourly.get(var)
            if not isinstance(values, list) or len(values) != 48:
                raise ValueError(f'Incomplete Open-Meteo hourly series for {var} at {lat},{lon}')
            array = np.asarray(values[:25], dtype=np.float64)
            if not np.isfinite(array).all():
                raise ValueError(f'Missing Open-Meteo values for {var} at {lat},{lon}')
            converted[var] = array
        if min(converted['precipitation']) < -0.0001 or min(converted['snowfall']) < -0.0001:
            raise ValueError('Open-Meteo returned negative precipitation or snowfall')
        validated.append((i, j, converted))
    return validated


def _part_file(day, locations):
    fingerprint = hashlib.sha256(json.dumps({
        'endpoint': ENDPOINT, 'day': day.isoformat(), 'params': _params(day, locations),
    }, sort_keys=True).encode()).hexdigest()[:24]
    return PARTS_DIR / (fingerprint + '.json.gz')


def _download_batch(day, locations):
    params = _params(day, locations)
    url = ENDPOINT + '?' + urlencode(params)
    # URL exceeds ordinary proxy limits if more locations are requested per batch.
    if len(url) > 6000:
        raise ValueError('Open-Meteo URL too long: reduce BATCH_SIZE')
    path = _part_file(day, locations)
    if path.exists():
        try:
            with gzip.open(path, 'rt', encoding='utf-8') as f:
                reply = json.load(f)
            return _validate_batch(reply, locations, day), path.stat().st_size, True
        except Exception as exc:
            LOG.warning('Discarding invalid cached Open-Meteo batch %s: %s', path, exc)
            path.unlink(missing_ok=True)
    try:
        with urlopen(url, timeout=90) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError('Open-Meteo response exceeds 8 MiB safety limit')
    except HTTPError as exc:
        message = exc.read(2048).decode('utf-8', errors='replace')
        if exc.code == 429:
            raise RuntimeError('Open-Meteo rate limit reached (HTTP 429); stop downloading and try later') from exc
        raise RuntimeError(f'Open-Meteo HTTP {exc.code}: {message[:500]}') from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f'Open-Meteo connectivity error: {exc}') from exc
    reply = json.loads(raw)
    records = _validate_batch(reply, locations, day)
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with gzip.open(tmp, 'wt', encoding='utf-8') as f:
            json.dump(reply, f, separators=(',', ':'))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return records, len(raw), False


def _assemble(day, roi, jid):
    import xarray as xr
    lats, lons, locations = _grid_points(roi)
    shape = (25, len(lats), len(lons))
    arrays = {var: np.full(shape, np.nan, dtype=np.float32) for var in VARIABLES}
    steps = math.ceil(len(locations) / BATCH_SIZE)
    _set(jid, total_steps=steps, stage=f'Preparing {len(locations)} ERA5 grid cells', phase='fetch')
    bytes_received = 0
    for index in range(steps):
        batch = locations[index*BATCH_SIZE:(index+1)*BATCH_SIZE]
        _set(jid, current_step=index+1, stage=f'Open-Meteo grid batch {index+1}/{steps}',
             phase='fetch')
        records, nbytes, cached = _download_batch(day, batch)
        for i, j, fields in records:
            for var, values in fields.items():
                arrays[var][:, i, j] = values
        bytes_received += nbytes if not cached else 0
        _set(jid, completed_steps=index+1, transferred_bytes=bytes_received,
             stage=f'{"Cached" if cached else "Retrieved"} Open-Meteo batch {index+1}/{steps}', phase='fetch')
    if any(not np.isfinite(a).all() for a in arrays.values()):
        raise ValueError('Incomplete Open-Meteo spatial weather grid')
    # snowfall is cm of snow depth equivalent; the documented Open-Meteo
    # ratio is 7 cm snow = 10 mm water equivalent. Convert to metres of SWE.
    # precipitation [mm] -> [m], temperature [C] -> [K], cloud [%] -> 0..1.
    def field(var, factor, offset, unit):
        return (('time','latitude','longitude'),
                (arrays[var] * factor + offset).astype(np.float32), {'units': unit})
    ds = xr.Dataset({
        'tp': field('precipitation', .001, 0, 'm'),
        'sf': field('snowfall', 1 / 7000, 0, 'm'),
        't2m': field('temperature_2m', 1, 273.15, 'K'),
        'd2m': field('dew_point_2m', 1, 273.15, 'K'),
        'lcc': field('cloud_cover_low', .01, 0, '(0 - 1)'),
    }, coords={
        'time': np.datetime64(day.isoformat()) + np.arange(25).astype('timedelta64[h]'),
        'latitude': lats, 'longitude': lons,
    })
    ds.attrs.update(source='Open-Meteo historical API (models=era5)',
                    provider='Open-Meteo', model='ERA5',
                    conversions='snowfall cm / 7 = mm water equivalent; mm / 1000 = m',
                    note='Grid-sampled API data, not original CDS NetCDF; approximate snow-water conversion')
    return ds


def _fetch(jid, day, roi):
    try:
        _set(jid, status='running', phase='fetch', stage='Connecting to Open-Meteo')
        ds = _assemble(day, roi, jid)
        _set(jid, phase='decode', stage='Validating 25-hour local weather NetCDF')
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(prefix='stratoq-open-meteo-') as tmp:
            file = Path(tmp) / 'era5-open-meteo.nc'
            try:
                import netCDF4  # noqa: F401
                ds.to_netcdf(file, engine='netcdf4', encoding={v: {'zlib': True, 'complevel': 3} for v in ds.data_vars})
            except ImportError:
                ds.to_netcdf(file, engine='scipy')
            meta = register_bytes(file.read_bytes(), day, filename=f'Open-Meteo ERA5 {day.isoformat()} UTC')
        _set(jid, status='complete', phase='ready', stage='Historical ERA5 weather ready (Open-Meteo)',
             dataset=meta, completed_steps=math.ceil(len(_grid_points(roi)[2])/BATCH_SIZE))
    except Exception as exc:
        LOG.error('[Open-Meteo %s] failed: %s\n%s', jid[:8], exc, traceback.format_exc())
        _set(jid, status='failed', phase='failed', stage='Open-Meteo ERA5 download failed',
             error=f'{type(exc).__name__}: {exc}. Completed batches remain cached for retry.')


def launch(date_utc, scenario):
    day = _date(date_utc)
    if day < date(1940, 1, 1):
        raise ValueError('Historical ERA5 data begins January 1, 1940')
    if day > datetime.now(timezone.utc).date() - timedelta(days=6):
        raise ValueError('ERA5 via Open-Meteo has an approximately five-day publication delay; choose an earlier UTC date')
    roi = roi_from_scenario(scenario)
    with _LOCK:
        for jid, old in list(_JOBS.items()):
            if old['status'] not in ('queued', 'running'):
                continue
            if old.get('worker_pid') != os.getpid():
                status(jid)
                continue
            if old.get('date_utc') == day.isoformat() and old.get('bounds') == {
                'north': roi[0], 'west': roi[1], 'south': roi[2], 'east': roi[3]
            }:
                return old.copy()
            raise ERA5BusyError('Another Open-Meteo download is already active; let it finish before requesting a different date or area')
        jid = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        job = {'id': jid, 'status': 'queued', 'stage': 'Waiting for Open-Meteo worker',
               'phase': 'queued', 'date_utc': day.isoformat(),
               'bounds': {'north': roi[0], 'west': roi[1], 'south': roi[2], 'east': roi[3]},
               'error': None, 'dataset': None, 'completed_steps': 0, 'total_steps': 0,
               'current_step': 0, 'transferred_bytes': 0, 'started_at': now,
               'updated_at': now, 'worker_pid': os.getpid()}
        if len(_JOBS) >= 20:
            for key in list(_JOBS):
                if _JOBS[key]['status'] in ('complete', 'failed'):
                    _JOBS.pop(key)
                    break
        _JOBS[jid] = job
        _persist(job)
        _POOL.submit(_fetch, jid, day, roi)
        return job.copy()


def status(jid):
    if len(jid) != 32 or any(c not in '0123456789abcdef' for c in jid):
        return None
    with _LOCK:
        job = _JOBS.get(jid)
        if job is None:
            path = JOBS_DIR / (jid + '.json')
            if not path.exists():
                return None
            try:
                job = json.loads(path.read_text())
            except (ValueError, OSError):
                return None
            _JOBS[jid] = job
        if job['status'] in ('queued', 'running') and job.get('worker_pid') != os.getpid():
            job.update(status='failed', phase='interrupted', stage='Backend restarted during retrieval',
                       error='FastAPI restarted during download. Retry; completed Open-Meteo batches remain cached.')
            _persist(job)
        return job.copy()
