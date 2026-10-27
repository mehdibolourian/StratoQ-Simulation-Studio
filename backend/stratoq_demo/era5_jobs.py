"""Resumable ERA5 single-level downloads for StratoQ Studio.

The selected UTC date needs its 24 hourly samples plus 00:00 of the next
UTC day. CDS may queue for minutes; a successful CDS *job* still has to
transfer the result. Daily responses are kept separately in a durable local
cache and the UI reports step completion (not fabricated CDS percentages).

For development use Uvicorn WITHOUT --reload, since any process restart kills
in-flight background threads. Durable job status detects a restart and points
the user to retry; already completed day files survive.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import RLock, Thread
import hashlib
import json
import logging
import os
import time
import traceback
import uuid

from .era5_weather import CACHE_DIR, _date, _open_bytes, register_bytes, roi_from_scenario

_LOG = logging.getLogger('uvicorn.error')
# Only one CDS retrieval is allowed locally at any given time.
_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='era5-fetch')
_LOCK = RLock()
_JOBS: dict[str, dict] = {}
PARTS_DIR = CACHE_DIR / 'daily'
JOBS_DIR = CACHE_DIR / 'jobs'
CDS_COLLECTION = 'reanalysis-era5-single-levels'
CDS_VARIABLES = ('total_precipitation', 'snowfall', '2m_temperature',
                 '2m_dewpoint_temperature', 'low_cloud_cover')
ALL_HOURS = [f'{h:02d}:00' for h in range(24)]
CDS_CLIENT_SETTINGS = dict(retry_max=3, sleep_max=10, timeout=120)
CDS_QUOTA_COOLDOWN_SECONDS = 600  # protect CDS from retry storms after explicit rejection
CDS_COOLDOWN_PATH = CACHE_DIR / 'cds-queue-cooldown.json'


class ERA5BusyError(RuntimeError):
    """A local CDS retrieval is already in progress. HTTP 409."""


class ERA5QueueLimitError(RuntimeError):
    """CDS recently rejected a job at its queue limit. HTTP 429."""


def _queue_pause_remaining():
    """Persisted pause protects CDS even if FastAPI is restarted."""
    try:
        info = json.loads(CDS_COOLDOWN_PATH.read_text())
        seconds = float(info['retry_after_epoch']) - time.time()
        if seconds > 0:
            return int(seconds) + 1
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return 0


def _note_cds_queue_rejection():
    CDS_COOLDOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
    target = CDS_COOLDOWN_PATH.with_name(CDS_COOLDOWN_PATH.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        target.write_text(json.dumps({'retry_after_epoch': time.time() + CDS_QUOTA_COOLDOWN_SECONDS}))
        os.replace(target, CDS_COOLDOWN_PATH)
    finally:
        target.unlink(missing_ok=True)


def _is_queue_limit_error(exc):
    message = str(exc).lower()
    return 'maximum number queued requests' in message or ('job has been rejected' in message and 'request data sequentially' in message)



def _persist(job):
    """Atomic, secret-free progress snapshots outlive Uvicorn restarts."""
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    dest = JOBS_DIR / (job['id'] + '.json')
    tmp = JOBS_DIR / (job['id'] + '.' + uuid.uuid4().hex + '.tmp')
    try:
        tmp.write_text(json.dumps(job, default=str))
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def _set(jid, **updates):
    with _LOCK:
        job = _JOBS[jid]
        job.update(updates)
        job['updated_at'] = datetime.now(timezone.utc).isoformat()
        _persist(job)


def _request(day, roi, hours):
    return {
        'product_type': ['reanalysis'], 'variable': list(CDS_VARIABLES),
        'year': str(day.year), 'month': f'{day.month:02d}',
        'day': f'{day.day:02d}', 'time': list(hours), 'area': list(roi),
        'data_format': 'netcdf', 'download_format': 'unarchived',
    }


def _part_path(request):
    fingerprint = hashlib.sha256(json.dumps({
        'collection': CDS_COLLECTION, 'request': request
    }, sort_keys=True).encode()).hexdigest()[:24]
    return PARTS_DIR / (fingerprint + '.cds')


def _verified_response(path, target_day, hours):
    """Validate actual hourly coordinates before trusting a cached download."""
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError('CDS returned an empty/missing file')
    ds = _open_bytes(path.read_bytes())
    coord = 'valid_time' if 'valid_time' in ds.coords else 'time'
    if coord not in ds.coords:
        raise ValueError('CDS file has no UTC time coordinate')
    import numpy as np
    available = set(np.asarray(ds[coord].values).astype('datetime64[h]').astype('int64').tolist())
    expected = {int(np.datetime64(f'{target_day.isoformat()}T{hour}').astype('datetime64[h]').astype('int64'))
                for hour in hours}
    if not expected.issubset(available):
        raise ValueError('CDS returned an incomplete or wrong-day dataset')
    return ds


def _get_part(jid, client, day, roi, hours, index, total):
    request = _request(day, roi, hours)
    path = _part_path(request)
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    day_label = f'{day.isoformat()} ({len(hours)} hour{"s" if len(hours)!=1 else ""})'
    if path.exists():
        try:
            ds = _verified_response(path, day, hours)
            _LOG.info('[ERA5 %s] reused cached CDS %s: %s bytes', jid[:8], day_label, path.stat().st_size)
            _set(jid, stage=f'Cached {day_label}', phase='cached',
                 transferred_bytes=path.stat().st_size)
            return ds
        except Exception as exc:
            _LOG.warning('[ERA5 %s] invalid cached file %s: %s', jid[:8], path, exc)
            path.unlink(missing_ok=True)

    # Separate per-job partial from completed cache. Never cache a partial file.
    partial = PARTS_DIR / (path.stem + '.' + jid + '.part')
    partial.unlink(missing_ok=True)
    _set(jid, phase='cds', stage=f'CDS queue / processing / transfer: {day_label}',
         current_day=day.isoformat(), current_step=index + 1, total_steps=total,
         transferred_bytes=0)
    _LOG.info('[ERA5 %s] CDS part %s/%s: %s, ROI=%s', jid[:8], index+1, total, day_label, roi)
    finished = {'done': False}
    # Poll filesystem during cdsapi.retrieve() to expose real bytes when its
    # streaming implementation writes to target. CDS often writes only at the
    # end; then the progress remains indeterminate instead of a fake 0%-100%.
    def observe():
        last = -1
        while not finished['done']:
            try:
                size = partial.stat().st_size if partial.exists() else 0
                if size != last:
                    _set(jid, transferred_bytes=size,
                         phase='transfer' if size > 0 else 'cds',
                         stage=(f'Transferring {day_label} ({size:,} bytes received)' if size > 0
                                else f'CDS queue / processing / transfer: {day_label}'))
                    last = size
            except Exception:
                _LOG.debug('Could not measure partial CDS file size', exc_info=True)
            time.sleep(1)
    watcher = Thread(target=observe, name='era5-byte-progress', daemon=True)
    watcher.start()
    try:
        client.retrieve(CDS_COLLECTION, request, str(partial))
        ds = _verified_response(partial, day, hours)
        os.replace(partial, path)
        _LOG.info('[ERA5 %s] saved CDS part %s/%s: %s (%s bytes)',
                  jid[:8], index + 1, total, path.name, path.stat().st_size)
        _set(jid, transferred_bytes=path.stat().st_size)
        return ds
    finally:
        finished['done'] = True
        watcher.join(timeout=2)
        partial.unlink(missing_ok=True)


def launch(date_utc, scenario):
    day = _date(date_utc)
    if day < date(1940, 1, 1):
        raise ValueError('ERA5 reanalysis starts in 1940')
    if day > datetime.now(timezone.utc).date() - timedelta(days=5):
        raise ValueError('ERA5 reanalysis is generally released about five days behind real time; select an older UTC date')
    roi = roi_from_scenario(scenario)
    with _LOCK:
        # Do not submit duplicate requests from repeated clicks or browser tabs.
        # Also prevent distinct dates from being sent in parallel through this
        # FastAPI server. Keep local job-status GET polling unrestricted.
        for old_jid, old in list(_JOBS.items()):
            if old['status'] not in ('queued', 'running'):
                continue
            if old.get('worker_pid') != os.getpid():
                status(old_jid)  # marks interrupted jobs from prior process
                continue
            if old.get('date_utc') == day.isoformat() and old.get('bounds') == {
                'north': roi[0], 'west': roi[1], 'south': roi[2], 'east': roi[3]
            }:
                _LOG.info('[ERA5 %s] duplicate local request: reusing active job', old_jid[:8])
                return old.copy()
            raise ERA5BusyError(
                f'Another ERA5 download ({old["date_utc"]}) is already active. '
                'Please let it complete before submitting a different CDS request.'
            )
        pause = _queue_pause_remaining()
        if pause:
            raise ERA5QueueLimitError(
                f'CDS rejected a request because its queue limit was reached. '
                f'To avoid repeated rejected submissions, StratoQ is pausing new CDS requests '
                f'for approximately {pause} more seconds. Check your CDS Your Requests page '
                'for other pending jobs. Existing local daily files remain cached.'
            )
        jid = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        job = {'id': jid, 'status': 'queued', 'stage': 'Waiting for local ERA5 worker',
               'phase': 'queued', 'date_utc': day.isoformat(),
               'bounds': {'north': roi[0], 'west': roi[1], 'south': roi[2], 'east': roi[3]},
               'error': None, 'dataset': None, 'completed_steps': 0, 'total_steps': 2,
               'current_step': 0, 'current_day': None, 'transferred_bytes': 0,
               'started_at': now, 'updated_at': now, 'worker_pid': os.getpid()}
        if len(_JOBS) >= 20:
            for key in list(_JOBS):
                if _JOBS[key]['status'] in ('complete', 'failed'):
                    _JOBS.pop(key)
                    break
        _JOBS[jid] = job
        _persist(job)
        _POOL.submit(_fetch, jid, day, roi)
        return job.copy()


def _fetch(jid, day, roi):
    try:
        try:
            import cdsapi
        except ImportError as exc:
            raise RuntimeError('Install cdsapi: python -m pip install "cdsapi>=0.7.7"') from exc
        if not Path.home().joinpath('.cdsapirc').exists():
            raise RuntimeError('Missing ~/.cdsapirc: configure CDS credentials and accept the ERA5 dataset licence')
        client = cdsapi.Client(**CDS_CLIENT_SETTINGS)
        next_day = day + timedelta(days=1)
        parts = [(day, ALL_HOURS), (next_day, ['00:00'])]
        _set(jid, status='running', stage='Connecting to CDS', phase='cds')
        datasets = []
        for i, (part_day, hours) in enumerate(parts):
            ds = _get_part(jid, client, part_day, roi, hours, i, len(parts))
            datasets.append(ds)
            _set(jid, completed_steps=i + 1, current_step=i + 1,
                 stage=f'ERA5 data ready: {i+1}/{len(parts)} requests', phase='part-ready')
        _set(jid, phase='decode', stage='Merging 25 hourly timestamps and validating NetCDF')
        import xarray as xr
        # Merge by *time*, not variable: each part contains the same fields at
        # disjoint hourly timestamps. xarray.merge aligns coordinates; strict
        # compat avoids hiding conflicting values on any duplicated timestamps.
        merged = xr.merge(datasets, compat='no_conflicts', join='outer')
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(prefix='stratoq-cds-') as temp:
            joined = Path(temp) / 'era5-merged.nc'
            try:
                import netCDF4  # noqa: F401
                merged.to_netcdf(joined, engine='netcdf4')
            except ImportError:
                merged.to_netcdf(joined, engine='scipy')
            meta = register_bytes(joined.read_bytes(), day,
                                  filename=f'CDS ERA5 {day.isoformat()} UTC')
        _set(jid, status='complete', phase='ready', stage='ERA5 downloaded and validated',
             completed_steps=2, dataset=meta, transferred_bytes=0)
    except Exception as exc:
        quota = _is_queue_limit_error(exc)
        if quota:
            _note_cds_queue_rejection()
            explanation = (
                'CDS rejected this request because the ERA5 dataset queue limit was reached. '
                'Do not immediately resubmit; check your CDS Your Requests page for outstanding '
                'jobs and try later. StratoQ allows only one local CDS retrieval at a time. '
                'This is a CDS server limit, not a download file-size or credentials error.'
            )
            _LOG.warning('[ERA5 %s] queue limit: %s', jid[:8], exc)
        else:
            explanation = f'{type(exc).__name__}: {exc}'
            _LOG.error('[ERA5 %s] failed: %s\n%s', jid[:8], exc, traceback.format_exc())
        _set(jid, status='failed', phase='cds-quota' if quota else 'failed',
             stage='CDS queue limit reached' if quota else 'ERA5 retrieval failed',
             error=explanation + '; completed daily files remain cached for retry')



def status(jid):
    # Old dev reload processes terminate in-flight threads. When a new process
    # receives a poll for that job, fail explicitly rather than showing forever.
    if not len(jid) == 32 or any(c not in '0123456789abcdef' for c in jid):
        return None
    with _LOCK:
        job = _JOBS.get(jid)
        if job is None:
            p = JOBS_DIR / (jid + '.json')
            if not p.exists():
                return None
            try:
                job = json.loads(p.read_text())
            except (ValueError, OSError):
                return None
            _JOBS[jid] = job
        if job['status'] in ('queued', 'running') and job.get('worker_pid') != os.getpid():
            job.update(status='failed', phase='interrupted', stage='Backend restarted during retrieval',
                       error='Uvicorn restarted while CDS was downloading. Restart without --reload and retry; completed daily files are cached.')
            _persist(job)
        return job.copy()
