import math
import pytest
from stratoq_demo.models import Scenario, Demand, SimulationConfig
from stratoq_demo.setup import default_scenario, build_links
from stratoq_demo.demand_profiles import demand_series, demand_rates


@pytest.mark.parametrize('duration,slots', [(10,8640),(30,2880),(60,1440),(300,288),(3600,24)])
def test_24_hour_defaults_cover_full_horizon(duration,slots):
    cfg = SimulationConfig.model_validate({'slot_seconds':duration})
    assert cfg.slots == slots
    assert cfg.slots * duration == 86400


@pytest.mark.parametrize('pattern', ['constant','diurnal','dual_peak','bursty'])
def test_profile_is_nonnegative_and_preserves_mean(pattern):
    d=Demand(id='d',source='a',target='b',rate_bps=4000,pattern=pattern)
    points=demand_series(d,288,300)
    assert len(points)==288
    assert min(points)>=0
    assert sum(points)/len(points)==pytest.approx(4000,rel=1e-9)
    if pattern!='constant':
        assert max(points)>4000 and min(points)<4000


def test_gaussian_peak_moves_with_peak_hour():
    d=Demand(id='d',source='a',target='b',rate_bps=4000,pattern='diurnal',peak_hour=17,peak_width_hours=2)
    points=demand_series(d,288,300)
    assert abs((points.index(max(points))+.5)*300/3600-17)<.25


def test_old_scenarios_keep_constant_mean():
    s=default_scenario()
    assert s.demands[0].pattern=='constant'
    assert demand_rates(s,3,300)['d-1']==[4000.]*3


def test_trajectory_horizon_uses_shortest_uploaded_trace(monkeypatch):
    from stratoq_demo import trajectories as tr
    s=default_scenario()
    s.balloons.append(s.balloons[0].model_copy(update={'id':'hap-2'}))
    for i,h in enumerate(s.balloons):
        h.trajectory_id=f'track-{i}'
        monkeypatch.setitem(tr.TRAJECTORIES,h.trajectory_id,dict(duration_seconds=[7200,3600][i]))
    assert tr.horizon_seconds(s)==3600


def test_backend_total_keys_are_actual_requested_integral(monkeypatch):
    from types import SimpleNamespace
    from stratoq_demo import resource_allocator as ra
    from stratoq_demo.allocator_algorithms import choose_paths
    s=default_scenario()
    s.config.slots=2
    records=ra.build_links(s)
    samples={(l['source'],l['target']):[l.copy(),l.copy()] for l in records}
    phy=SimpleNamespace(system=SimpleNamespace(THETA=300),slots=2,
        rate_by_link={l['id']:[5000.,5000.] for l in records},scene_links=samples,
        rate_stats={'computed':2,'cached':0})
    monkeypatch.setattr(ra,'require_gurobi',lambda:object())
    monkeypatch.setattr(ra,'create_physical_network',lambda scenario,progress=None:phy)
    def select(scenario,rates,buffers,caps,seconds,algorithm,seed,n_samples,gp,trace):
        paths=choose_paths(scenario,rates,buffers,seconds,'scar_q')
        trace.update(candidate_solves=1,gurobi_runtime_seconds=.001,
            gurobi_version='13.0.3',solver_status='OPTIMAL',selected_paths=1,activated_links=2,
            candidate_paths=1,positive_capacity_links=2,gurobi_variable_count=9,
            gurobi_constraint_count=8,selection_note='test')
        return paths, ({'d-1':2000.},{},{},set(rates),buffers,600000.)
    monkeypatch.setattr(ra,'select_and_solve_slot',select)
    r=ra.allocate(s)
    assert r.summary['total_served_bits']==1200000
    assert r.summary['total_requested_bits']==2400000
    assert r.summary['total_satisfaction']==.5
    assert r.summary['horizon_seconds']==600


def test_full_horizon_offline_uses_gurobi_and_intertemporal_qkp():
    gp=pytest.importorskip('gurobipy')
    from stratoq_demo.offline_allocator import solve_offline
    s=default_scenario()
    s.config.allocation_mode='optimal'
    s.config.optimality_gap=0.0
    records=[build_links(s),build_links(s)]
    left,right=[link['id'] for link in records[0]]
    rates=[{left:5000.,right:5000.},{left:0.,right:0.}]
    series={'d-1':[4000.,4000.]}
    result,summary=solve_offline(s,records,rates,{left:1000000.,right:1000000.},series,300,gp)
    assert summary['gurobi_status']=='OPTIMAL'
    assert summary['gurobi_optimized_models']==1
    assert sum(frame['served']['d-1'] for frame in result)==pytest.approx(5000,abs=.01)
    assert sum(frame['served']['d-1'] for frame in result[1:])>0
    assert not result[1]['activated']


def test_trajectory_duration_is_last_minus_first_timestamp():
    from stratoq_demo.trajectories import parse_trajectory
    csv_data = ("Time_s,Longitude_deg,Latitude_deg,Altitude_m\n"
                "100,279,48.6,15000\n"
                "160,279.1,48.7,15000\n").encode()
    trajectory = parse_trajectory("offset.csv", csv_data)
    assert trajectory['duration_seconds'] == 60
    assert trajectory['times'] == [0, 60]
