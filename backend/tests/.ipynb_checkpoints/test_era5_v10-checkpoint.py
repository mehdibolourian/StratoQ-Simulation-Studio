"""Synthetic NetCDF test fixture only. Production code never synthesizes weather."""
from datetime import date,timedelta
import numpy as np
import xarray as xr
import pytest
from fastapi.testclient import TestClient
from stratoq_demo.era5_weather import ERA5Cube, frame_at, register_bytes, get_cube, roi_from_scenario, humidity
from stratoq_demo.setup import default_scenario
from stratoq_demo.models import Scenario
from main import app

DAY='2026-01-10'

def make_dataset(day=DAY):
    t0=np.datetime64(day+'T00:00:00')
    times=t0+np.arange(26).astype('timedelta64[h]')
    lats=[48.25,48.5,48.75,49.0]
    lons=[-81.75,-81.5,-81.25,-81.0,-80.75,-80.5,-80.25]
    shape=(26,len(lats),len(lons))
    tp=np.zeros(shape);sf=np.zeros(shape)
    tp[1,:,:]=.001 # hour 00–01: 1 mm/h
    tp[2,:,:]=.003 # hour 01–02: 3 mm/h
    sf[2,:,:]=.001 # second hour: 1 mm/h snow + 2 rain
    # Rest of day: fog proxy after noon (instant fields)
    t2m=np.full(shape,273.15+12)
    d2m=np.full(shape,273.15+4)
    d2m[13:,:,:]=273.15+11.9
    lcc=np.zeros(shape);lcc[13:,:,:]=.9
    ds=xr.Dataset({
        'tp':(('time','latitude','longitude'),tp,{'units':'m'}),
        'sf':(('time','latitude','longitude'),sf,{'units':'m'}),
        't2m':(('time','latitude','longitude'),t2m,{'units':'K'}),
        'd2m':(('time','latitude','longitude'),d2m,{'units':'K'}),
        'lcc':(('time','latitude','longitude'),lcc,{'units':'(0 - 1)'})},
        coords={'time':times,'latitude':lats,'longitude':lons})
    return ds

@pytest.fixture
def cube():
    return ERA5Cube.from_dataset(make_dataset(),DAY,'era5-fixture','fixture.nc')

def test_era5_accumulation_intervals_and_conservation(cube):
    a=cube.frame(0,1800)
    assert a['rain'][0,0]==pytest.approx(1)
    b=cube.frame(1800,3600)
    assert b['rain'][0,0]==pytest.approx(1.5) # .5h at 1 mm/h and .5h at 2 mm/h
    assert b['snow'][0,0]==pytest.approx(.5)
    # Across exact hour: rain 1mm + 2mm, snow 0+1mm
    all2=cube.frame(0,7200)
    assert all2['rain'][0,0]==pytest.approx(1.5)
    assert all2['snow'][0,0]==pytest.approx(.5)

def test_era5_hourly_switch_and_fog_proxy(cube):
    f1=cube.frame(3600,3600)
    assert f1['snow'][0,0]==pytest.approx(1)
    f2=cube.frame(15*3600,300)
    assert f2['rain'][0,0]==pytest.approx(0)
    assert f2['fog'].all()
    assert f2['rh'].min()>.97
    assert (cube.frame(0,300)['fog']==False).all()

def test_era5_spatial_and_path_attenuation(cube):
    scenario=default_scenario()
    gs=scenario.ground_stations[0]
    hap=scenario.balloons[0]
    first=cube.frame(0,300)
    second=cube.frame(3600,300)
    late=cube.frame(14*3600,300)
    a,fa=cube.link_attenuation(gs,hap,first)
    b,fb=cube.link_attenuation(gs,hap,second)
    f,ff=cube.link_attenuation(gs,hap,late)
    assert a>0 and b>a
    assert fb[2]==1 and fb[1]==1 and fa[2]==0
    assert f>0 and ff[0]==1
    assert f!=pytest.approx(a)

def test_no_extrapolation_and_grid_validation(cube):
    with pytest.raises(ValueError, match='UTC day'):
        cube.frame(86400,300)
    scenario=default_scenario()
    cube.validate_area(scenario)
    scenario.ground_stations[0].lon=-90
    with pytest.raises(ValueError,match='does not cover'):
        cube.validate_area(scenario)

def test_era5_region_generation_is_display_only(cube):
    a=cube.regions(cube.frame(0,300))
    assert a and a[0]['source']=='era5' and not a[0]['editable']
    assert all(w['effect']=='rain' for w in a)
    b=cube.regions(cube.frame(3600,300))
    assert {w['effect'] for w in b}=={'rain','snow'}
    c=cube.regions(cube.frame(14*3600,300))
    assert {w['effect'] for w in c}=={'fog'}

def test_era5_upload_and_api(monkeypatch):
    import stratoq_demo.era5_weather as ew
    monkeypatch.setattr(ew,'CACHE_DIR', __import__('pathlib').Path(__import__('tempfile').mkdtemp()))
    ds=make_dataset()
    bytes_nc=bytes(ds.to_netcdf(engine='scipy'))
    response=TestClient(app).post('/api/era5/upload',data={'date_utc':DAY},files={'file':('historical.nc',bytes_nc,'application/x-netcdf')})
    assert response.status_code==200,response.text
    meta=response.json()
    assert meta['date_utc']==DAY
    assert meta['grid']==[4,7]
    frame=TestClient(app).get(f"/api/era5/datasets/{meta['dataset_id']}/frame",params={'date_utc':DAY,'slot_seconds':300,'slot':0})
    assert frame.status_code==200,frame.text
    assert len(frame.json()['regions'])>0
    assert get_cube(meta['dataset_id'],DAY).metadata()['date_utc']==DAY

def test_era5_never_silent_fallback():
    scenario=default_scenario()
    scenario.config.weather_source='era5'
    scenario.config.era5_date=DAY
    scenario.config.era5_dataset_id='unknown-id'
    from stratoq_demo.era5_weather import scenario_era5
    with pytest.raises(ValueError,match='not found'):
        scenario_era5(scenario)

def test_era5_manual_additive_with_same_real_rate_path(cube,monkeypatch):
    import stratoq_demo.era5_weather as ew
    monkeypatch.setitem(ew._CUBES,'era5-fixture',cube)
    scenario=default_scenario()
    scenario.config.slots=2
    scenario.config.slot_seconds=3600
    scenario.config.weather_source='era5';scenario.config.era5_date=date.fromisoformat(DAY)
    scenario.config.era5_dataset_id='era5-fixture'
    from stratoq_demo import physical_setup
    # Test only: replace the actual expensive channel evaluator, NOT geometry/ERA5.
    from stratoq_demo import real_rates
    monkeypatch.setattr(physical_setup,'calculate_key_rate_mac_real',
                        lambda directed,physical,optical,**kwargs: ([[100.]*physical.slots for _ in directed],{'computed':0,'cached':0}))
    without=physical_setup.create_physical_network(scenario)
    loss=without.scene_links[('gs-1','hap-1')][0]['weather_loss_db']
    assert loss>0
    from stratoq_demo.models import WeatherRegion
    scenario.weather_regions=[WeatherRegion(id='weather-1',name='Manual rain',lat=48.6,lon=-81.0,
        radius_km=60,effect='rain',precipitation_rate_mm_h=5,attenuation_db=0)]
    with_manual=physical_setup.create_physical_network(scenario)
    with_loss=with_manual.scene_links[('gs-1','hap-1')][0]['weather_loss_db']
    assert with_loss>loss
    assert with_manual.scene_links[('gs-1','hap-1')][0]['weather_flags'][1]==1
    # Explicitly turning ERA5 off retains manually specified region only.
    scenario.config.weather_source='manual'
    static=physical_setup.create_physical_network(scenario)
    assert 0<static.scene_links[('gs-1','hap-1')][0]['weather_loss_db']<with_loss

def test_era5_humidity_ratio():
    assert humidity(280,280)==pytest.approx(1)
    assert humidity(290,270)<.3

def test_historical_output_uses_real_rate_formula_and_visuals(cube,monkeypatch,tmp_path):
    import stratoq_demo.era5_weather as ew
    from stratoq_demo import real_rates
    from stratoq_demo.stratoq_adapter import simulate
    monkeypatch.setitem(ew._CUBES,'era5-fixture',cube)
    monkeypatch.setattr(real_rates,'CACHE_PATH',tmp_path/'independent-cache.db')
    monkeypatch.setattr(real_rates,'evaluate_theoretical_point',lambda _: .2)
    scenario=default_scenario()
    scenario.config.slots=2;scenario.config.slot_seconds=3600
    scenario.config.weather_source='era5';scenario.config.era5_date=date.fromisoformat(DAY)
    scenario.config.era5_dataset_id='era5-fixture'
    result=simulate(scenario)
    assert len(result.frames)==2
    first=result.frames[0]
    second=result.frames[1]
    assert first.links and first.historical_weather_regions
    assert 'date_utc' in first.historical_weather_metadata
    assert first.links[0].weather_loss_db>0
    assert second.links[0].weather_loss_db>first.links[0].weather_loss_db
    assert second.links[0].capacity_bps<first.links[0].capacity_bps
    assert first.stored_bits_total>=0
    assert first.links[0].weather_flags[1]==1
    assert second.links[0].weather_flags[2]==1
    assert result.engine=='balloon-qnet-theoretical'


def test_era5_zip_multiple_variables(monkeypatch,tmp_path):
    from io import BytesIO
    import zipfile
    import stratoq_demo.era5_weather as ew
    monkeypatch.setattr(ew,'CACHE_DIR',tmp_path)
    ds=make_dataset()
    output=BytesIO()
    with zipfile.ZipFile(output,'w') as archive:
        for name in ('tp','sf','t2m','d2m','lcc'):
            archive.writestr(f'{name}.nc',bytes(ds[[name]].to_netcdf(engine='scipy')))
    meta=register_bytes(output.getvalue(),DAY,'cds.zip')
    assert meta['grid']==[4,7]
    assert get_cube(meta['dataset_id'],DAY).frame(0,300)['rain'][0,0]==pytest.approx(1)


def test_era5_malformed_data_rejected():
    dataset=make_dataset()
    dataset['tp'].attrs['units']='mm'
    with pytest.raises(ValueError,match='metres of water equivalent'):
        ERA5Cube.from_dataset(dataset,DAY)

def test_fake_cds_two_day_retrieval_pipeline(monkeypatch, tmp_path):
    """25 requested samples, 24+1; daily files are durable and reused."""
    import sys, types
    import stratoq_demo.era5_jobs as jobs
    import stratoq_demo.era5_weather as ew
    monkeypatch.setattr(ew, 'CACHE_DIR', tmp_path/'cache')
    monkeypatch.setattr(jobs, 'PARTS_DIR', tmp_path/'daily')
    monkeypatch.setattr(jobs, 'JOBS_DIR', tmp_path/'jobs')
    monkeypatch.setattr(jobs.Path, 'home', classmethod(lambda cls: tmp_path))
    (tmp_path/'.cdsapirc').write_text('fixture, not credentials')
    seen = []
    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs['retry_max'] == 3
        def retrieve(self, dataset, spec, target):
            assert dataset == 'reanalysis-era5-single-levels'
            day = f"{spec['year']}-{spec['month']}-{spec['day']}"
            hours = spec['time']
            seen.append((day, hours))
            ds = make_dataset(day).isel(time=slice(0, len(hours)))
            __import__('pathlib').Path(target).write_bytes(bytes(ds.to_netcdf(engine='scipy')))
    monkeypatch.setitem(sys.modules, 'cdsapi', types.SimpleNamespace(Client=FakeClient))
    jid = 'f' * 32
    jobs._JOBS[jid] = {'id':jid,'status':'queued','stage':'queued','error':None,'dataset':None,
                       'completed_steps':0,'total_steps':2,'worker_pid':__import__('os').getpid()}
    jobs._fetch(jid, date.fromisoformat(DAY), [49.5,-82,48,-80])
    status = jobs.status(jid)
    assert status['status'] == 'complete', status['error']
    assert status['completed_steps'] == 2
    assert seen == [(DAY,[f'{h:02}:00' for h in range(24)]),('2026-01-11',['00:00'])]
    loaded = get_cube(status['dataset']['dataset_id'],DAY)
    assert loaded.frame(0,3600)['rain'][0,0] == pytest.approx(1)
    # Second identical request must reuse both independently cached days.
    another='e'*32
    jobs._JOBS[another] = {'id':another,'status':'queued','stage':'queued','error':None,'dataset':None,
                          'completed_steps':0,'total_steps':2,'worker_pid':__import__('os').getpid()}
    jobs._fetch(another,date.fromisoformat(DAY),[49.5,-82,48,-80])
    assert jobs.status(another)['status']=='complete'
    assert len(seen)==2


def test_cds_second_day_failure_resume(monkeypatch,tmp_path):
    """If CDS fails on midnight sample, first day's response survives."""
    import sys,types,os
    import stratoq_demo.era5_jobs as jobs
    import stratoq_demo.era5_weather as ew
    monkeypatch.setattr(ew,'CACHE_DIR',tmp_path/'cache')
    monkeypatch.setattr(jobs,'PARTS_DIR',tmp_path/'daily')
    monkeypatch.setattr(jobs,'JOBS_DIR',tmp_path/'jobs')
    monkeypatch.setattr(jobs.Path,'home',classmethod(lambda cls:tmp_path))
    (tmp_path/'.cdsapirc').write_text('test fixture')
    requested=[]
    fail_next=[True]
    class FakeClient:
        def __init__(self,**kw):pass
        def retrieve(self,name,spec,target):
            day=f"{spec['year']}-{spec['month']}-{spec['day']}"
            requested.append(day)
            if day=='2026-01-11' and fail_next[0]:
                raise TimeoutError('Simulated CDS interruption')
            ds=make_dataset(day).isel(time=slice(0,len(spec['time'])))
            __import__('pathlib').Path(target).write_bytes(bytes(ds.to_netcdf(engine='scipy')))
    monkeypatch.setitem(sys.modules,'cdsapi',types.SimpleNamespace(Client=FakeClient))
    for jid in ('c'*32,'d'*32):
        jobs._JOBS[jid]={'id':jid,'status':'queued','stage':'queued','error':None,'dataset':None,
                       'completed_steps':0,'total_steps':2,'worker_pid':os.getpid()}
        jobs._fetch(jid,date.fromisoformat(DAY),[49.5,-82,48,-80])
        if fail_next[0]:
            assert jobs.status(jid)['status']=='failed'
            assert jobs.status(jid)['completed_steps']==1
            fail_next[0]=False
        else:
            assert jobs.status(jid)['status']=='complete'
    assert requested==[DAY,'2026-01-11','2026-01-11']


def test_era5_job_restart_detected(monkeypatch,tmp_path):
    import stratoq_demo.era5_jobs as jobs
    monkeypatch.setattr(jobs,'JOBS_DIR',tmp_path/'jobs')
    jid='b'*32
    jobs._JOBS.pop(jid,None)
    (tmp_path/'jobs').mkdir()
    (tmp_path/'jobs'/(jid+'.json')).write_text(__import__('json').dumps(
        {'id':jid,'status':'running','stage':'downloading','worker_pid':-1}))
    state=jobs.status(jid)
    assert state['status']=='failed'
    assert 'restarted' in state['error'].lower()
