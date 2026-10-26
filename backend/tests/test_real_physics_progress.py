"""Regression: upstream physics is invoked, cache is geometry-specific, progress is real."""
import math
import time
from fastapi.testclient import TestClient
from main import app
from stratoq_demo import real_rates
from stratoq_demo.setup import default_scenario
from stratoq_demo.resource_allocator import allocate


def test_real_channel_invocation_and_incremental_invalidation(monkeypatch):
    original=real_rates.evaluate_theoretical_point
    calls=[]
    def spy(task):
        calls.append(task)
        return original(task)
    monkeypatch.setattr(real_rates,'evaluate_theoretical_point',spy)
    scenario=default_scenario();scenario.config.slots=2
    statuses=[]
    first=allocate(scenario,progress=statuses.append)
    assert len(calls)==4  # 2 GS × 1 HAP × uplink/downlink; both slots share geometry
    assert any(status['stage']=='channel' and status['completed']==4 for status in statuses)
    assert first.summary['physical_evaluations']==4
    assert first.summary['cached_evaluations']==0
    second=allocate(scenario)
    assert second.summary['physical_evaluations']==0
    assert second.summary['cached_evaluations']==4
    assert len(calls)==4
    # Only one GS's directional pair changes, not the unaffected GS pair.
    scenario.ground_stations[0].lat+=0.001
    third=allocate(scenario)
    assert third.summary['physical_evaluations']==2
    assert third.summary['cached_evaluations']==2
    assert len(calls)==6
    # QBER changes the SKR but not optical eta: no new expensive work.
    previous=third.frames[0].links[0].capacity_bps
    scenario.config.optical.qber+=0.02
    fourth=allocate(scenario)
    assert fourth.summary['physical_evaluations']==0
    assert fourth.frames[0].links[0].capacity_bps < previous
    # Changing optical configuration MUST invalidate upstream eta cache.
    scenario.config.optical.cn0*=0.9
    fifth=allocate(scenario)
    assert fifth.summary['physical_evaluations']==4


def test_weather_uses_same_upstream_clear_sky_efficiency():
    from stratoq_demo.models import WeatherRegion
    scenario=default_scenario();scenario.config.slots=2
    base=allocate(scenario)
    scenario.weather_regions=[WeatherRegion(id='fog',name='Fog',lat=scenario.balloons[0].lat,
                                           lon=scenario.balloons[0].lon,effect='fog',radius_km=50,
                                           attenuation_db=6)]
    wet=allocate(scenario)
    assert wet.summary['physical_evaluations']==0
    assert math.isclose(wet.frames[0].links[0].capacity_bps/base.frames[0].links[0].capacity_bps,
                        10**(-0.6), rel_tol=1e-4)


def test_job_progress_endpoint():
    client=TestClient(app)
    s=default_scenario();s.config.slots=3
    start=client.post('/api/simulations',json=s.model_dump())
    assert start.status_code==202,start.text
    jid=start.json()['id']
    statuses=[]
    for _ in range(120):
        state=client.get(f'/api/simulations/{jid}').json()
        statuses.append(state)
        if state['status'] in ('complete','failed'):break
        time.sleep(.05)
    assert statuses[-1]['status']=='complete', statuses[-1]
    assert statuses[-1]['stage']=='complete'
    assert statuses[-1]['completed']==statuses[-1]['total']
    assert client.get(f'/api/simulations/{jid}/result').json()['engine']=='balloon-qnet-theoretical'
    assert client.get('/api/physics/status').json()['channel_import_ok']


def test_missing_native_dependency_fails_loudly(monkeypatch):
    from balloon_qnet import transmittance
    def bad_lowtran(*args,**kw):
        raise RuntimeError('Missing LOWTRAN7 native library')
    monkeypatch.setattr(transmittance,'slant',bad_lowtran)
    scenario=default_scenario();scenario.config.slots=1
    import pytest
    with pytest.raises(RuntimeError,match='LOWTRAN7'):
        allocate(scenario)
