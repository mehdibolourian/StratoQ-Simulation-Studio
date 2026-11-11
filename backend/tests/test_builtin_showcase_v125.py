"""v1.2.5: embedded trajectories, faithful translations, timed physical weather.

Does not substitute heuristic optical rates or claim end-to-end MILP results.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app
from stratoq_demo.models import Scenario
from stratoq_demo.trajectories import TRAJECTORIES, horizon_seconds, sample, scenario_at
from stratoq_demo.setup import build_links
from stratoq_demo.demand_profiles import demand_rates
from stratoq_demo.scheduled_weather import weather_at

PRESET_PATH = Path(__file__).resolve().parent.parent / 'stratoq_demo/builtin_experiments.json'
PRESETS = json.loads(PRESET_PATH.read_text())['experiments']


def scenario(name):
    return Scenario.model_validate(next(p['scenario'] for p in PRESETS if p['id'] == name))


def test_valid_presets_same_algorithm_comparison_and_qkp_pair():
    assert len(PRESETS) == 4
    a,b,on,off = (scenario(x) for x in ('corridor-scar','corridor-mcr','qkp-enabled','qkp-disabled'))
    # Everything physical is identical. The two online experiments differ
    # from the QKP-on Optimal experiment only in allocation_mode.
    assert all(s.config.horizon_seconds==86400 and s.config.slots==144 for s in (a,b,on,off))
    assert all(s.config.slot_seconds==600 for s in (a,b,on,off))
    for other in (b,on,off):
        assert a.ground_stations == other.ground_stations
        assert a.balloons == other.balloons
        assert a.demands == other.demands
        assert a.weather_regions == other.weather_regions
        assert a.link_overrides == other.link_overrides
        assert a.config.optical == other.config.optical
    assert [x.config.allocation_mode for x in (a,b,on,off)] == ['scar_q','mcr_q','optimal','optimal']
    assert a.config.qkp_enabled and b.config.qkp_enabled and on.config.qkp_enabled
    assert off.config.qkp_enabled is False
    assert on.model_dump(exclude={'config':{'qkp_enabled'}}) == off.model_dump(exclude={'config':{'qkp_enabled'}})
    assert len(on.ground_stations)==3 and len(on.balloons)==1 and len(on.demands)==2
    assert all(s.balloons[0].trajectory_id=='builtin:csv-ontario-24h' for s in (a,b,on,off))
    assert on.balloons[0].n_tx==on.balloons[0].n_rx==2
    assert on.balloons[0].capacity_bits/3 >= 150_000_000
    profile=demand_rates(on,144,600)
    shared_requested=sum(sum(values[42:102])*600 for values in profile.values())
    assert shared_requested < on.balloons[0].capacity_bits/3


def test_builtin_traces_survive_registry_reset_and_can_be_translated():
    s = scenario('corridor-scar')
    t1 = s.balloons[0].trajectory_id
    TRAJECTORIES.clear()  # Simulates backend restart.
    raw0 = sample(t1,0); raw1=sample(t1,3600)
    snap0,_ = scenario_at(s,0)
    snap1,_ = scenario_at(s,3600)
    h0,h1=snap0.balloons[0],snap1.balloons[0]
    assert h0.lat == pytest.approx(s.balloons[0].trajectory_start_lat)
    assert h0.lon == pytest.approx(s.balloons[0].trajectory_start_lon)
    assert h1.lat-h0.lat == pytest.approx(raw1['lat']-raw0['lat'])
    assert h1.lon-h0.lon == pytest.approx(raw1['lon']-raw0['lon'])
    assert h1.altitude_km == pytest.approx(raw1['altitude_km'])
    s.balloons[0].trajectory_origin_mode='original'
    unshifted,_=scenario_at(s,0)
    assert unshifted.balloons[0].lat==pytest.approx(raw0['lat'])
    assert unshifted.balloons[0].lon==pytest.approx(raw0['lon'])
    assert horizon_seconds(s)==86400


def test_timed_weather_modifies_real_path_attenuation_and_visual_snapshots():
    s=scenario('qkp-enabled')
    snaps = [scenario_at(s,t)[0] for t in [0,27000,41400,72000]]
    assert len(snaps[0].weather_regions)==0
    assert len(snaps[1].weather_regions)==1
    assert len(snaps[2].weather_regions)==2
    assert len(snaps[3].weather_regions)==0
    clear=build_links(snaps[0]);storm=build_links(snaps[2]);late=build_links(snaps[3])
    assert sum(row['weather_loss_db'] for row in clear)==0
    assert max(row['weather_loss_db'] for row in storm) > 1
    assert sum(row['weather_loss_db'] for row in late)==0
    # Fog attenuates the actual uplink route; no impact if region absent.
    fog=s.weather_regions[0]
    at_ramp=weather_at(fog, 25500)
    at_peak=weather_at(fog, 27600)
    assert at_ramp.visibility_km > at_peak.visibility_km
    assert fog.visibility_km==.06  # Input is never overwritten.


def test_time_horizon_limit_also_without_trajectory():
    s=scenario('qkp-enabled')
    s.balloons[0].trajectory_id=None
    assert horizon_seconds(s) == 86400


def test_builtin_endpoints_return_stable_validated_presets():
    client=TestClient(app)
    response=client.get('/api/experiments/builtin')
    assert response.status_code==200
    assert len(response.json()['experiments'])==4
    assert all('scenario' not in p for p in response.json()['experiments'])
    selected=client.get('/api/experiments/builtin/qkp-enabled')
    assert selected.status_code==200
    assert Scenario.model_validate(selected.json()['scenario']).config.qkp_enabled
    assert client.get('/api/experiments/builtin/qkp-disabled').status_code==200
    assert client.get('/api/experiments/builtin/unknown').status_code==404


def test_physical_preparation_uses_scheduled_weather_snapshots(monkeypatch):
    # Integration-only stub of the expensive LOWTRAN evaluation: this test
    # validates geometry/weather handoff without claiming genuine SKR values.
    import stratoq_demo.physical_setup as phys
    def dummy_rates(links, network, optical, progress=None, max_workers=None):
        return [[1800.]*network.slots for _ in links], {'cached':0,'computed':0}
    monkeypatch.setattr(phys,'calculate_key_rate_mac_real',dummy_rates)
    p = phys.create_physical_network(scenario('qkp-enabled'))
    assert p.slots == 144
    tracked = p.scene_links[('gs-if','hap-storm')]
    assert tracked[0]['weather_loss_db'] == 0
    assert tracked[69]['weather_loss_db'] > 1
    assert tracked[143]['weather_loss_db'] == 0
    assert len(p.rate_by_link[('gs-if:hap-storm')]) == 144


def test_full_day_csv_trace_ends_at_24_hours_without_early_clamping():
    from stratoq_demo.trajectories import _load
    full = _load('builtin:csv-ontario-24h')
    excerpt = _load('builtin:csv-ontario-6h')
    assert full['duration_seconds'] == 86400
    assert excerpt['duration_seconds'] == 21600
    assert full['rows'] == 1441
    assert sample('builtin:csv-ontario-24h', 86400)['lon'] != sample('builtin:csv-ontario-24h', 18000)['lon']
    on=scenario('qkp-enabled')
    assert horizon_seconds(on)==86400
    assert on.balloons[0].trajectory_duration_seconds==86400
    # A geographic shift still preserves relative motion over a full day.
    first,_=scenario_at(on,0)
    last,_=scenario_at(on,86400)
    a=sample('builtin:csv-ontario-24h',0)
    b=sample('builtin:csv-ontario-24h',86400)
    assert last.balloons[0].lat-first.balloons[0].lat==pytest.approx(b['lat']-a['lat'])


def test_timed_milestone_events_are_inside_grid_and_identical_for_matched_runs():
    for p in PRESETS:
        s=Scenario.model_validate(p['scenario'])
        events=p['milestones']
        assert len(events)>=3
        assert all(0<=e['seconds']<s.config.horizon_seconds for e in events)
        assert all(e['title'] and e['why'] and e['details'] for e in events)
        assert all(0<=min(s.config.slots-1, __import__('math').ceil(e['seconds']/s.config.slot_seconds))<s.config.slots for e in events)
    assert all(p['milestones']==PRESETS[0]['milestones'] for p in PRESETS)
    qkp=[p['milestones'] for p in PRESETS if p['id']=='qkp-enabled'][0]
    assert [m['seconds'] for m in qkp]==[0,25200,37800,61200]
    on=scenario('qkp-enabled')
    assert on.weather_regions[0].active_until_seconds-on.weather_regions[0].active_from_seconds==36000


def test_frontend_backend_presets_in_sync():
    root=Path(__file__).resolve().parents[2]
    front=json.loads((root/'frontend/src/lib/builtinExperiments.json').read_text())
    back=json.loads(PRESET_PATH.read_text())
    assert front==back
    assert all('milestones' in p for p in front['experiments'])


def test_camera_and_menu_regression_source_wiring():
    # Browser/OrbitControls behavior needs manual QA; these checks catch the
    # previously broken version-scoped CSS and hard-coded camera direction.
    root=Path(__file__).resolve().parents[2]
    css=(root/'frontend/src/styles.css').read_text()
    three=(root/'frontend/src/components/Network3D.jsx').read_text()
    app=(root/'frontend/src/App.jsx').read_text()
    assert '.app-shell .header-file-options' in css
    assert 'ref={filesMenuRef}' in app
    assert 'filesMenuRef.current.open=false' in app
    assert 'previousDirection.normalize()' in three
    assert 'frame && fittedRef.current' in three
    assert 'camera.position.copy(target).addScaledVector(direction,cameraDistance)' in three
    assert 'camera.position.set(centerX+cameraDistance' not in three
