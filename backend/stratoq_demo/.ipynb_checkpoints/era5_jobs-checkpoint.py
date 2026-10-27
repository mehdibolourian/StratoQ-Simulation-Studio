"""CDS ERA5 historical-data retrieval jobs. No synthetic or cached wrong-date fallback.

CDS credentials are read server-side from ~/.cdsapirc (never sent to browser).
CDS requests can be queued for a long time; the polling API reports stages.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
from threading import RLock
import logging
import traceback
import uuid
from pathlib import Path
from .era5_weather import roi_from_scenario, register_bytes, _date

_LOG=logging.getLogger('uvicorn.error')
_POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='era5-fetch')
_LOCK=RLock()
_JOBS={}


def launch(date_utc,scenario):
    day=_date(date_utc)
    if day<date(1940,1,1):
        raise ValueError('ERA5 reanalysis starts in 1940')
    if day>date.today()-timedelta(days=5):
        raise ValueError('ERA5 reanalysis is generally released about five days behind real time; select an older UTC date')
    roi=roi_from_scenario(scenario)
    jid=uuid.uuid4().hex
    job={'id':jid,'status':'queued','stage':'queued','date_utc':day.isoformat(),
         'bounds':{'north':roi[0],'west':roi[1],'south':roi[2],'east':roi[3]},
         'error':None,'dataset':None}
    with _LOCK:
        if len(_JOBS)>=15:
            for key in list(_JOBS):
                if _JOBS[key]['status'] in ('complete','failed'):_JOBS.pop(key);break
        _JOBS[jid]=job
    _POOL.submit(_fetch,jid,day,roi)
    return job.copy()


def _set(jid,**kw):
    with _LOCK:_JOBS[jid].update(kw)


def _fetch(jid,day,roi):
    _set(jid,status='running',stage='requesting CDS ERA5 (queue may take time)')
    try:
        try:
            import cdsapi
        except ImportError as exc:
            raise RuntimeError('Install cdsapi in backend: python -m pip install cdsapi') from exc
        if not Path.home().joinpath('.cdsapirc').exists():
            raise RuntimeError('Missing ~/.cdsapirc. Configure a Copernicus CDS API token and accept the ERA5 single-level dataset licence. See ERA5-HISTORICAL-V10.md')
        tomorrow=day+timedelta(days=1)
        _LOG.info('[ERA5 %s] requesting 48 hourly timesteps for %s, bounds N/W/S/E=%s',jid[:8],day,roi)
        request={'product_type':['reanalysis'],
                 'variable':['total_precipitation','snowfall','2m_temperature','2m_dewpoint_temperature','low_cloud_cover'],
                 'year':[str(day.year),str(tomorrow.year)],
                 'month':sorted({f'{day.month:02d}',f'{tomorrow.month:02d}'}),
                 'day':sorted({f'{day.day:02d}',f'{tomorrow.day:02d}'}),
                 'time':[f'{hr:02d}:00' for hr in range(24)],
                 'area':roi,'data_format':'netcdf','download_format':'unarchived'}
        # Request year/month/day Cartesian product can include other dates near a
        # boundary; retrieve each date separately and merge to eliminate ambiguity.
        from tempfile import TemporaryDirectory
        with TemporaryDirectory(prefix='stratoq-cds-') as temp:
            client=client = cdsapi.Client(
                                retry_max=3,
                                sleep_max=10,
                                timeout=120,
                            )
            paths=[]
            for i,target_day in enumerate([day,tomorrow]):
                spec={**request,'year':str(target_day.year),'month':f'{target_day.month:02d}',
                      'day':f'{target_day.day:02d}'}
                output=Path(temp)/f'era5-part{i}.download'
                _set(jid,stage=f'downloading ERA5 {target_day.isoformat()} (CDS may queue)')
                client.retrieve('reanalysis-era5-single-levels',spec,str(output))
                paths.append(output)
            _set(jid,stage='decoding ERA5 NetCDF')
            # Archive responses often contain zipped NetCDF partitions. Register
            # merged NetCDF with the existing validation code.
            from .era5_weather import _open_bytes
            import xarray as xr
            datasets=[]
            for p in paths:
                datasets.append(_open_bytes(p.read_bytes()))
            merged=xr.merge(datasets,compat='no_conflicts',join='outer')
            joined=Path(temp)/'era5-merged.nc'
            try:
                import netCDF4  # noqa: F401; handles NetCDF4/HDF5 and richer CDS metadata
                merged.to_netcdf(joined,engine='netcdf4')
            except ImportError:
                merged.to_netcdf(joined,engine='scipy')
            meta=register_bytes(joined.read_bytes(),day,filename=f'CDS ERA5 {day.isoformat()} UTC')
        _set(jid,status='complete',stage='ready',dataset=meta)
    except Exception as exc:
        _LOG.error('[ERA5 %s] failed: %s\n%s',jid[:8],exc,traceback.format_exc())
        _set(jid,status='failed',stage='failed',error=f'{type(exc).__name__}: {exc}')


def status(jid):
    with _LOCK:
        job=_JOBS.get(jid)
        return job.copy() if job else None
