"""Regression checks for persisted historical-weather IDs and recovery endpoint.

No Open-Meteo network calls and no physical approximation are used.
"""
from datetime import date
import numpy as np
import xarray as xr
from fastapi.testclient import TestClient
import stratoq_demo.era5_weather as weather
from main import app


def _fixture_netcdf():
    shape = (25, 2, 2)
    timestamp = np.datetime64('2024-06-21T00:00')
    values = dict(
        tp=(np.zeros(shape, dtype='f4'), 'm'),
        sf=(np.zeros(shape, dtype='f4'), 'm'),
        t2m=(np.full(shape, 290, dtype='f4'), 'K'),
        d2m=(np.full(shape, 280, dtype='f4'), 'K'),
        lcc=(np.zeros(shape, dtype='f4'), '(0 - 1)'),
    )
    dataset = xr.Dataset({k:(('time','latitude','longitude'),v,{'units':unit})
                          for k,(v,unit) in values.items()}, coords={
        'time': timestamp+np.arange(25).astype('timedelta64[h]'),
        'latitude':[48.5,48.75], 'longitude':[-81.,-80.75],
    })
    return dataset.to_netcdf(engine='scipy')


def test_persisted_dataset_survives_in_memory_cache_reset(tmp_path, monkeypatch):
    monkeypatch.setattr(weather, 'CACHE_DIR', tmp_path)
    weather._CUBES.clear()
    meta=weather.register_bytes(_fixture_netcdf(),date(2024,6,21),'fixture.nc')
    assert (tmp_path/(meta['dataset_id']+'.json')).is_file()
    weather._CUBES.clear()  # same as restarting FastAPI
    client=TestClient(app)
    r=client.get('/api/era5/datasets/'+meta['dataset_id']+'/metadata',
                 params={'date_utc':'2024-06-21'})
    assert r.status_code==200, r.text
    assert r.json()['dataset_id']==meta['dataset_id']
    assert r.json()['date_utc']=='2024-06-21'
    weather._CUBES.clear()


def test_missing_dataset_returns_explicit_404_without_fabrication(tmp_path, monkeypatch):
    monkeypatch.setattr(weather,'CACHE_DIR',tmp_path)
    weather._CUBES.clear()
    response=TestClient(app).get('/api/era5/datasets/'+'0'*20+'/metadata',
                                  params={'date_utc':'2024-06-21'})
    assert response.status_code==404
    assert not list(tmp_path.glob('*.nc'))
