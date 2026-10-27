"""Offline, mocked Open-Meteo integration: no external API access."""
from datetime import date, datetime, time, timedelta
import io
import json
from urllib.parse import parse_qs, urlparse

import numpy as np
import pytest
from fastapi.testclient import TestClient

from main import app
from stratoq_demo import open_meteo_jobs as jobs
from stratoq_demo import era5_weather as weather
from stratoq_demo.setup import default_scenario


class FakeResponse:
    def __init__(self, content):
        self.content = content
    def __enter__(self): return io.BytesIO(self.content)
    def __exit__(self,*args): pass


def make_reply(url, changed_units=False, missing_values=False, shifted_coords=False):
    params=parse_qs(urlparse(url).query)
    lats=list(map(float, params['latitude'][0].split(',')))
    lons=list(map(float, params['longitude'][0].split(',')))
    day=date.fromisoformat(params['start_date'][0])
    assert params['models']==['era5']
    assert params['cell_selection']==['nearest']
    assert params['elevation']==[','.join(['nan'] * len(lats))]
    assert len(params['elevation'][0].split(',')) == len(lats) == len(lons)
    assert params['timezone']==['GMT']
    assert params['end_date']==[(day+timedelta(days=1)).isoformat()]
    times=[(datetime.combine(day,time())+timedelta(hours=h)).strftime('%Y-%m-%dT%H:%M') for h in range(48)]
    units=jobs.UNITS.copy()
    if changed_units: units['snowfall']='mm'
    answers=[]
    for lat,lon in zip(lats,lons):
        answers.append({
            'latitude':lat+(0.25 if shifted_coords else 0), 'longitude':lon,
            'utc_offset_seconds':0, 'hourly_units':units,
            'hourly':{
                'time':times,
                'temperature_2m':[5]*48,
                'dew_point_2m':[4.9]*48,
                'precipitation':[1]*48,
                'snowfall':[0.7]*48,
                'cloud_cover_low':[90]*48,
            },
        })
        if missing_values: answers[-1]['hourly']['snowfall'][1]=None
    return answers[0] if len(answers)==1 else answers


class FakeExecutor:
    def __init__(self): self.submissions=[]
    def submit(self, fn, *args): self.submissions.append((fn,args))
    def execute(self):
        while self.submissions:
            fn, args=self.submissions.pop(0)
            fn(*args)


@pytest.fixture
def isolated(monkeypatch,tmp_path):
    monkeypatch.setattr(jobs,'_JOBS',{})
    monkeypatch.setattr(jobs,'JOBS_DIR',tmp_path/'jobs')
    monkeypatch.setattr(jobs,'PARTS_DIR',tmp_path/'parts')
    monkeypatch.setattr(weather,'CACHE_DIR',tmp_path/'weather')
    with weather._LOCK: weather._CUBES.clear()
    with weather._FRAME_LOCK: weather._FRAME_CACHE.clear()
    executor=FakeExecutor()
    monkeypatch.setattr(jobs,'_POOL',executor)
    requested=[]
    def fake_urlopen(url, timeout):
        requested.append(url)
        return FakeResponse(json.dumps(make_reply(url)).encode())
    monkeypatch.setattr(jobs,'urlopen',fake_urlopen)
    return executor, requested


def test_assembled_grid_and_physical_unit_conversions(isolated):
    executor, requests=isolated
    s=default_scenario()
    job=jobs.launch('2024-10-15',s)
    assert len(executor.submissions)==1
    assert jobs.launch('2024-10-15',s)['id']==job['id']
    with pytest.raises(jobs.ERA5BusyError): jobs.launch('2024-10-16',s)
    executor.execute()
    ready=jobs.status(job['id'])
    assert ready['status']=='complete',ready.get('error')
    assert ready['total_steps']==len(requests)
    assert len(requests)>0
    cube=weather.get_cube(ready['dataset']['dataset_id'],'2024-10-15')
    assert cube.arrays['tp'][1,0,0]==pytest.approx(.001)
    assert cube.arrays['sf'][1,0,0]==pytest.approx(.0001)
    assert cube.arrays['t2m'][1,0,0]==pytest.approx(278.15,rel=1e-6)
    assert cube.arrays['d2m'][1,0,0]==pytest.approx(278.05,rel=1e-6)
    assert cube.arrays['lcc'][1,0,0]==pytest.approx(.9,rel=1e-6)
    frame=cube.frame(0,3600)
    assert frame['rain'][0,0]==pytest.approx(.9,rel=1e-5)
    assert frame['snow'][0,0]==pytest.approx(.1,rel=1e-5)
    assert 'Open-Meteo' in cube.metadata()['source']
    assert 'Open-Meteo' in cube.metadata()['precipitation_quality']
    assert cube.bounds['west'] <= min(node.lon for node in s.ground_stations)
    cube.validate_area(s)
    # Cache reused without querying internet when asking again for the same date/ROI.
    before=len(requests)
    again=jobs.launch('2024-10-15',s)
    executor.execute()
    assert jobs.status(again['id'])['status']=='complete'
    assert len(requests)==before


def test_api_job_status_and_preview(isolated):
    executor, requests=isolated
    client=TestClient(app)
    payload={'date_utc':'2024-10-15','scenario':default_scenario().model_dump(mode='json')}
    first=client.post('/api/open-meteo/jobs',json=payload)
    assert first.status_code==202,first.text
    same=client.post('/api/open-meteo/jobs',json=payload)
    assert same.json()['id']==first.json()['id']
    payload['date_utc']='2024-10-16'
    assert client.post('/api/open-meteo/jobs',json=payload).status_code==409
    executor.execute()
    ready=client.get(f'/api/open-meteo/jobs/{first.json()["id"]}').json()
    assert ready['status']=='complete',ready.get('error')
    meta=ready['dataset']
    preview=client.get(f'/api/era5/datasets/{meta["dataset_id"]}/frame',
                       params={'date_utc':'2024-10-15','slot_seconds':3600,'slot':0})
    assert preview.status_code==200,preview.text
    assert isinstance(preview.json()['regions'],list)


def test_reject_nonmatching_units_missing_data_and_wrong_grid():
    locations=[(0,0,48.5,-81.0)]
    params=jobs._params(date(2024,10,15),locations)
    url=jobs.ENDPOINT+'?'+__import__('urllib.parse').parse.urlencode(params)
    for options, error in [({'changed_units':True},'unit'),
                           ({'missing_values':True},'Missing'),
                           ({'shifted_coords':True},'snapped')]:
        with pytest.raises(ValueError,match=error):
            jobs._validate_batch(make_reply(url,**options),locations,date(2024,10,15))


def test_no_cds_credentials_or_cds_import_needed(isolated,monkeypatch):
    executor,requests=isolated
    # No .cdsapirc, and no cdsapi import. Background retrieval still works.
    jobs.launch('2024-10-15',default_scenario())
    executor.execute()
    assert requests


def test_multilocation_elevation_values_match_coordinates():
    """Regression: API HTTP 400 if a single nan accompanies multiple locations."""
    locations = [(0, 0, 48.5, -81.0), (0, 1, 48.5, -80.75),
                 (1, 0, 48.75, -81.0)]
    params = jobs._params(date(2024, 10, 15), locations)
    assert params['latitude'].count(',') == 2
    assert params['longitude'].count(',') == 2
    assert params['elevation'] == 'nan,nan,nan'
    assert params['cell_selection'] == 'nearest'
    assert params['models'] == 'era5'
