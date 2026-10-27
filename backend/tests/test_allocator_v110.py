"""Pure policy tests run anywhere; Gurobi integration runs when Gurobi is installed."""
import pytest
from stratoq_demo.models import Scenario
from stratoq_demo.setup import default_scenario
from stratoq_demo.allocator_algorithms import choose_paths, candidate_paths, solve_slot, select_and_solve_slot


def test_legacy_exports_migrate_to_real_algorithms():
    source=default_scenario().model_dump()
    source['config']['allocation_mode']='random'
    assert Scenario.model_validate(source).config.allocation_mode == 'mcr_q'
    source['config']['allocation_mode']='greedy'
    assert Scenario.model_validate(source).config.allocation_mode == 'scar_q'


def test_two_policies_select_supported_paths_and_respect_ports():
    s=default_scenario()
    other=s.balloons[0].model_copy(update={'id':'hap-2', 'name':'Other'})
    s.balloons.append(other)
    a,b=s.ground_stations
    rates={f'{g.id}:{h.id}': 5000 for g in (a,b) for h in s.balloons}
    rates[f'{a.id}:hap-2']=6000
    rates[f'{b.id}:hap-2']=6000
    buffers={k:0. for k in rates}
    scar=choose_paths(s,rates,buffers,300,'scar_q')
    mcr=choose_paths(s,rates,buffers,300,'mcr_q')
    assert len(scar)==len(mcr)==1
    assert mcr[0].hap_id in {'hap-1', 'hap-2'}
    assert scar[0].uplink_id.startswith(a.id+':')


def test_disabled_links_and_no_keys_are_infeasible():
    s=default_scenario()
    rates={'gs-1:hap-1':0.,'gs-2:hap-1':4000.}
    assert not choose_paths(s,rates,{k:0 for k in rates},300,'scar_q')
    # Notebook SCAR-Q needs both fresh links OR both stored links to cover
    # the full request; mixed partial inventory is not a feasible candidate.
    assert not choose_paths(s,rates,{'gs-1:hap-1':1500000,'gs-2:hap-1':0},300,'scar_q')
    assert choose_paths(s,rates,{'gs-1:hap-1':1500000,'gs-2:hap-1':1500000},300,'scar_q')


def test_gurobi_slot_lp_and_storage_balance():
    gp=pytest.importorskip('gurobipy')
    s=default_scenario()
    links={'gs-1:hap-1':5000.,'gs-2:hap-1':5000.}
    prev={k:0. for k in links}
    paths=choose_paths(s,links,prev,300,'scar_q')
    served,live,saved,active,next_buffers,obj=solve_slot(paths,links,prev,{k:2e6 for k in links},300,gp)
    assert served['d-1']==pytest.approx(4000.)
    assert active==set(links)
    assert all(next_buffers[k]==pytest.approx(300000.) for k in links)
    links={'gs-1:hap-1':0.,'gs-2:hap-1':0.}
    served,live,saved,active,next_buffers,obj=solve_slot(paths,links,next_buffers,{k:2e6 for k in links},300,gp)
    assert served['d-1']==pytest.approx(1000.)
    assert not active
    assert all(next_buffers[k]==pytest.approx(0.) for k in links)


def test_backend_frame_wires_algorithm_activation_without_physics_change(monkeypatch):
    """Integration seam: preserve physical results and expose solver activity."""
    from types import SimpleNamespace
    from stratoq_demo import resource_allocator as ra
    s=default_scenario()
    s.config.slots=1
    links=ra.build_links(s)
    samples={(l['source'],l['target']):[{**l}] for l in links}
    phy=SimpleNamespace(system=SimpleNamespace(THETA=300),slots=1,
        rate_by_link={l['id']:[5000.] for l in links},scene_links=samples,
        rate_stats={'computed':2,'cached':0})
    monkeypatch.setattr(ra,'require_gurobi',lambda:object())
    monkeypatch.setattr(ra,'create_physical_network',lambda scenario,progress=None:phy)
    def mock_solved(paths,rates,buffers,caps,seconds,gp=None):
        assert len(paths)==1
        return {'d-1':4000.}, {}, {}, set(rates), {k:300000. for k in rates}, 1.2e6
    from stratoq_demo.allocator_algorithms import choose_paths
    def fake_select(scenario,rates,buffers,caps,seconds,algorithm,seed,n_samples,gp,trace=None):
        paths=choose_paths(scenario,rates,buffers,seconds,algorithm)
        if trace is not None:
            trace.update(candidate_solves=1, gurobi_runtime_seconds=.005,
                         gurobi_version='13.0.0', solver_status='OPTIMAL',
                         selected_paths=len(paths), activated_links=2, candidate_paths=1,
                         positive_capacity_links=2, gurobi_variable_count=12,
                         gurobi_constraint_count=16, selection_note='Active optical links highlighted')
        return paths, mock_solved(paths,rates,buffers,caps,seconds,gp)
    monkeypatch.setattr(ra,'select_and_solve_slot',fake_select)
    result=ra.allocate(s)
    assert result.summary['algorithm']=='scar_q'
    frame=result.frames[0]
    assert frame.served_bps_total==4000.
    assert all(x.active and x.activated and x.allocated for x in frame.links)
    assert frame.stored_bits_total==600000.
    assert frame.optimizer['solver_status']=='OPTIMAL'
    assert frame.optimizer['candidate_solves']==1
    assert frame.optimizer['selected_paths']==1
    assert result.summary['gurobi_optimized_models']==1
    assert result.summary['gurobi_runtime_seconds']==.005


def test_mcr_random_route_samples_are_reproducible():
    import random
    s = default_scenario()
    s.balloons.append(s.balloons[0].model_copy(update={'id': 'hap-2'}))
    rates = {f'{g.id}:{h.id}': 5000. for g in s.ground_stations for h in s.balloons}
    buffers = {k: 0. for k in rates}
    sequence_one = [choose_paths(s, rates, buffers, 300, 'mcr_q', rng=random.Random(i))[0].hap_id
                    for i in range(50)]
    sequence_two = [choose_paths(s, rates, buffers, 300, 'mcr_q', rng=random.Random(i))[0].hap_id
                    for i in range(50)]
    assert sequence_one == sequence_two
    assert set(sequence_one) == {'hap-1', 'hap-2'}  # Not highest capacity routing


def test_scarq_orders_scarce_demands_and_uses_least_contended_path():
    s = default_scenario()
    from stratoq_demo.models import Demand
    # Two competing demands share the same HAP terminals; the higher-rate
    # demand wins equal scarcity and the HAP one-connection constraint.
    s.demands = [Demand(id='small', source='gs-1', target='gs-2', rate_bps=1000),
                 Demand(id='large', source='gs-1', target='gs-2', rate_bps=4000)]
    rates = {'gs-1:hap-1':5000, 'gs-2:hap-1':5000}
    paths = choose_paths(s, rates, {k:0. for k in rates}, 300, 'scar_q')
    assert len(paths) == 1
    assert paths[0].demand_id == 'large'


def test_mcr_solves_all_candidates_and_commits_only_best(monkeypatch):
    from stratoq_demo import allocator_algorithms as aa
    s=default_scenario()
    s.balloons.append(s.balloons[0].model_copy(update={'id':'hap-2'}))
    rates = {f'{g.id}:{h.id}': 1000. if h.id == 'hap-1' else 5000.
             for g in s.ground_stations for h in s.balloons}
    buffers = {k:100. for k in rates}
    snapshots=[]
    def mock_solve(paths, current_rates, current_buffers, storage, duration, gp=None):
        snapshots.append((tuple(p.hap_id for p in paths), dict(current_buffers)))
        val = (min(paths[0].available_bps, paths[0].requested_bps)
               if paths else 0.)
        # Losing samples must not overwrite `buffers` on the next sample.
        return {'d-1':val}, {}, {}, set(), {'winner':val}, val * duration
    monkeypatch.setattr(aa,'solve_slot',mock_solve)
    chosen, result = select_and_solve_slot(s, rates, buffers, {}, 300, 'mcr_q',
                                           seed=12, n_samples=25)
    assert len(snapshots) == 25
    assert all(b == buffers for _,b in snapshots)
    assert chosen[0].hap_id == 'hap-2'
    assert result[-1] == 4000 * 300
    chosen_again, result_again = select_and_solve_slot(s,rates,buffers,{},300,
                                            'mcr_q',seed=12,n_samples=25)
    assert chosen == chosen_again
    assert result == result_again


def test_scarq_uses_single_gurobi_evaluation_regardless_of_sample_count(monkeypatch):
    from stratoq_demo import allocator_algorithms as aa
    s=default_scenario()
    rates={'gs-1:hap-1':5000.,'gs-2:hap-1':5000.}
    calls=[]
    def fake_solve(paths, rates, buffers, capacity, duration, gp=None):
        calls.append(paths)
        return {},{},{},set(),{},0.
    monkeypatch.setattr(aa,'solve_slot',fake_solve)
    select_and_solve_slot(s,rates,{}, {},300,'scar_q',n_samples=99)
    assert len(calls)==1


def test_invalid_sample_count_and_migration():
    from pydantic import ValidationError
    s=default_scenario().model_dump()
    s['config']['mcr_samples']=0
    with pytest.raises(ValidationError): Scenario.model_validate(s)
    s['config']['mcr_samples']=3
    assert Scenario.model_validate(s).config.mcr_samples==3


def test_gurobi_trace_comes_from_each_optimize_call(monkeypatch):
    """Trace must use reported results from the solve stage, not sample count alone."""
    from stratoq_demo import allocator_algorithms as aa
    s=default_scenario()
    rates={'gs-1:hap-1':2000., 'gs-2:hap-1':2000.}
    buffers={k:0. for k in rates}
    optimized=[]
    def fake_solve(paths, rates, buffers, max_storage, duration, gp=None, diagnostics=None):
        optimized.append(paths)
        if diagnostics is not None:
            diagnostics.update(optimize_called=True, status='OPTIMAL', runtime_seconds=.003,
                               variables=11, constraints=15, gurobi_version='13.0.0')
        return ({p.demand_id: 2000. for p in paths}, {}, {},
                set(rates) if paths else set(), buffers.copy(), 2000.*duration if paths else 0.)
    monkeypatch.setattr(aa,'solve_slot',fake_solve)
    scar_trace={}
    chosen,solved=aa.select_and_solve_slot(s,rates,buffers,{},300,'scar_q',
                                            trace=scar_trace)
    assert not chosen
    assert scar_trace['candidate_solves']==1
    assert scar_trace['solver_status']=='OPTIMAL'
    assert scar_trace['positive_capacity_links']==2
    assert scar_trace['selected_paths']==0
    assert 'No feasible full-rate' in scar_trace['selection_note']
    mcr_trace={}
    chosen,solved=aa.select_and_solve_slot(s,rates,buffers,{},300,'mcr_q',
                                            n_samples=3,trace=mcr_trace)
    assert chosen
    assert mcr_trace['candidate_solves']==3
    assert mcr_trace['selected_paths']==1
    assert mcr_trace['activated_links']==2
    assert mcr_trace['gurobi_runtime_seconds']==.009
    assert len(optimized)==4


def test_real_gurobi_audit_integration_if_available():
    gp=pytest.importorskip('gurobipy')
    s=default_scenario()
    rates={'gs-1:hap-1':5000.,'gs-2:hap-1':5000.}
    buffers={k:0. for k in rates}
    diag={}
    paths,solved=select_and_solve_slot(s,rates,buffers,{k:2e6 for k in rates},300,
                                      'scar_q',gp=gp,trace=diag)
    assert diag['candidate_solves']==1
    assert diag['solver_status']=='OPTIMAL'
    assert diag['gurobi_variable_count']>0
    assert diag['gurobi_constraint_count']>0
    assert diag['selected_paths']==1
    assert diag['activated_links']==2
    assert solved[-1]==pytest.approx(4000*300)
