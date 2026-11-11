"""Learning Lab correctness: topology dimensions, strict masks, real PPO update,
shared Studio result schema, and stable demand-key indexing.

No fake optical rates are ever substituted by production: these synthetic
fixtures exist ONLY in unit tests that exercise the wiring without Gurobi.
"""
from __future__ import annotations
from types import SimpleNamespace
import numpy as np
import pytest

from stratoq_demo.learning_core import (
    topology_shape, port_mask, demand_indices, sequential_masks,
    observation, paper_shaped_reward, make_policy, sample_choices, ppo_update,
)
from stratoq_demo.learning_presets import preset_scenario
from stratoq_demo import learning_worker


def synthetic_physical(scenario):
    class Node:
        def __init__(self,tag):self.tag=tag
    nodes={n.id:Node(n.id) for n in [*scenario.ground_stations,*scenario.balloons]}
    links=[];rates={};scene={}
    slots=scenario.config.slots
    for g in scenario.ground_stations:
        for h in scenario.balloons:
            links.extend([SimpleNamespace(n1=nodes[g.id],n2=nodes[h.id],K_MAX=[9000]*slots),
                          SimpleNamespace(n1=nodes[h.id],n2=nodes[g.id],K_MAX=[9000]*slots)])
            rates[f'{g.id}:{h.id}']=[6000]*slots
            scene[(g.id,h.id)]=[{'distance_km':66,'elevation_deg':15,'in_range':True,
                                'weather_loss_db':0.,'weather_flags':(0,0,0)}]*slots
    return SimpleNamespace(links=links, rate_by_link=rates,scene_links=scene,slots=slots)


def test_shape_scales_with_network_and_never_zero_pads():
    small=preset_scenario(12)
    shape=topology_shape(small)
    assert (shape.n_links,shape.observation_dim,shape.logits_dim)==(12,102,8)
    assert len(observation(small,synthetic_physical(small),0,{},
               {d.id:d.rate_bps for d in small.demands}))==102
    big=small.model_copy(deep=True)
    extra=big.balloons[0].model_copy(update={'id':'hap-99','name':'Another HAP'})
    big.balloons.append(extra)
    big.demands.append(big.demands[0].model_copy(update={'id':'d-99'}))
    newshape=topology_shape(big)
    assert newshape.n_links==18
    assert newshape.observation_dim==7*18+6*4
    assert newshape.logits_dim==3*5
    assert newshape.observation_dim!=shape.observation_dim
    assert make_policy(shape).actor.out_features==shape.logits_dim
    assert make_policy(newshape).actor.out_features==newshape.logits_dim


def test_mask_prevents_repeat_demands_and_gs_terminal_collisions():
    sc=preset_scenario(); ports=demand_indices(sc)
    mask=np.ones((2,4),dtype=bool)
    # d0 and d2 have distinct sources, same dest? d0 Timmins->Iroquois and
    # d2 Iroquois->Cochrane, so no same TX or RX; d1 Cochrane->Timmins.
    seq=sequential_masks(mask,[1],*ports)
    assert not seq[1,1]  # demand cannot be used by both HAPs
    # artificial duplicate-source demand -> same GS cannot Tx twice
    conflicting=list(ports[0]);conflicting[2]=conflicting[0]
    seq=sequential_masks(mask,[1],conflicting,ports[1],ports[2],ports[3])
    assert not seq[1,3]
    with pytest.raises(ValueError):sequential_masks(mask,[1,1],*ports)


def test_reward_uses_stable_demand_ids_not_active_list_positions():
    req={'d4':100,'d9':100}
    assert paper_shaped_reward({'d4':90,'d9':0},{'d4':30,'d9':20},
                               {'d4':30,'d9':20},req)!=paper_shaped_reward(
                               {'d4':0,'d9':90},{'d4':30,'d9':20},{'d4':30,'d9':20},req)
    assert paper_shaped_reward({}, {}, {}, {})==0.


def test_actual_pytorch_masked_ppo_gradient_step():
    import torch
    sc=preset_scenario(); shape=topology_shape(sc);policy=make_policy(shape)
    observation_array=np.zeros(shape.observation_dim,dtype=np.float32)
    allowed=np.ones((shape.n_haps,shape.n_demands+1),dtype=bool)
    ports=demand_indices(sc)
    records=[]
    for k in range(5):
        actions,lp,v=sample_choices(policy,observation_array,allowed,ports)
        records.append(dict(obs=observation_array,mask=allowed,choices=actions,
                            logp=lp,value=v,reward=k*.2))
    before=policy.actor.weight.detach().clone()
    stats=ppo_update(policy,torch.optim.Adam(policy.parameters(),lr=0.001),records,ports)
    assert np.isfinite(list(stats.values())).all()
    assert not torch.equal(before,policy.actor.weight)


def test_training_episode_returns_real_studio_frames(monkeypatch):
    sc=preset_scenario(12); physical=synthetic_physical(sc)
    _,all_rates,storage=learning_worker.base_rates_and_storage(sc,physical)
    def fake_solve(paths,rates,buffers,max_storage,duration,gp=None):
        served={p.demand_id:min(p.requested_bps,4000.) for p in paths}
        live={};saved={};active=set()
        for p in paths:
            active.update((p.uplink_id,p.downlink_id))
        return served,live,saved,active,buffers.copy(),sum(served.values())*duration
    def fake_baseline(actual,rates,buffers,max_storage,duration,algorithm,seed,n_samples=1,gp=None):
        solved=fake_solve([],rates,buffers,max_storage,duration)
        return [],solved
    monkeypatch.setattr(learning_worker,'solve_slot',fake_solve)
    monkeypatch.setattr(learning_worker,'select_and_solve_slot',fake_baseline)
    p=make_policy(topology_shape(sc))
    schedule=learning_worker.rate_schedule(sc,sc.config.slots,sc.config.slot_seconds)
    training=learning_worker.run_episode(p,sc,physical,all_rates,storage,None,schedule,
        demand_indices(sc),training=True,make_frames=False)
    assert len(training['rollout'])==12
    evaluation=learning_worker.run_episode(p,sc,physical,all_rates,storage,None,schedule,
        demand_indices(sc),training=False,make_frames=True)
    assert len(evaluation['frames'])==12
    assert len(evaluation['frames'][0]['links'])==6
    assert len(evaluation['frames'][0]['demands'])==3
    assert len(evaluation['frames'][0]['qkps'])==5


def test_complete_worker_pipeline_with_mocked_physics_and_lp(monkeypatch,tmp_path):
    """Integration smoke test for persistence and checkpoints; *not* physics validation."""
    from stratoq_demo.learning_presets import PRESET
    class TestModel:
        def __init__(self,*args,**kwargs):pass
        Params=SimpleNamespace(OutputFlag=0)
        def addVar(self,**kwargs):return None
        def optimize(self):return None
        def dispose(self):return None
    fake_gp=SimpleNamespace(Model=TestModel)
    monkeypatch.setattr(learning_worker,'require_gurobi',lambda:fake_gp)
    monkeypatch.setattr(learning_worker,'create_physical_network',lambda scenario,progress=None:synthetic_physical(scenario))
    def fake_solve(paths,rates,buffers,max_storage,duration,gp=None):
        served={p.demand_id:min(p.requested_bps,3000.) for p in paths}
        return served,{}, {},set(lid for p in paths for lid in (p.uplink_id,p.downlink_id)),buffers.copy(),sum(served.values())*duration
    def fake_baseline(actual,rates,buffers,max_storage,duration,algorithm,seed,n_samples=1,gp=None):
        # Separate known baseline with real Gurobi replaced only during unit testing.
        return [],fake_solve([],rates,buffers,max_storage,duration)
    monkeypatch.setattr(learning_worker,'solve_slot',fake_solve)
    monkeypatch.setattr(learning_worker,'select_and_solve_slot',fake_baseline)
    job=tmp_path/'abc123'
    job.mkdir()
    learning_worker.write_json(job/'config.json',{'preset':PRESET,'slots':12,
                                                  'episodes':2,'checkpoint_every':1,'seed':42})
    learning_worker.train(job)
    import json
    state=json.loads((job/'status.json').read_text())
    metrics=json.loads((job/'metrics.json').read_text())
    evaluation=json.loads((job/'evaluation_000002.json').read_text())
    assert state['status']=='complete'
    assert [c['episode'] for c in state['checkpoints']]==[0,1,2]
    assert len(metrics)==2
    assert len(evaluation['frames'])==12
    assert (job/'checkpoint_000000.pt').exists()


def test_curriculum_uses_progressive_topology_relative_demands():
    schedules={'d0':[1.]*3,'d1':[1.]*3,'d2':[1.]*3}
    rng=np.random.default_rng(42)
    for episode,expected in [(1,1),(4,1),(5,2),(9,2),(10,3),(30,3)]:
        active,count=learning_worker.curriculum_schedule(schedules,episode,30,rng)
        assert count==expected
        assert sum(any(v) for v in active.values())==expected
        assert all(all(x==0 for x in values) or values==[1.]*3 for values in active.values())


def test_custom_studio_network_is_snapshotted_and_scales_policy():
    from stratoq_demo.learning_presets import validate_learning_scenario
    from pydantic import ValidationError
    sc=preset_scenario(12).model_dump(mode='json')
    sc['ground_stations'].append({'id':'gs-new','name':'New GS','lat':49.1,'lon':-81.1,'n_tx':2,'n_rx':2})
    sc['balloons'].append({'id':'hap-new','name':'Extra HAP','lat':49.0,'lon':-81.0})
    sc['demands'].append({'id':'d-new','source':'gs-new','target':'gs-timmins','rate_bps':1100})
    sc['link_overrides']=[{'source':'gs-new','target':'hap-new','enabled':False,'visibility_km':42}]
    validated=validate_learning_scenario(sc,24)
    sh=topology_shape(validated)
    assert validated.config.slots==24 and validated.config.slot_seconds==300
    assert (sh.n_gs,sh.n_haps,sh.n_demands)==(4,3,4)
    assert (sh.observation_dim,sh.logits_dim)==(7*24+24,3*5)
    assert validated.link_overrides[0].visibility_km==42
    assert sc['config']['slots']==12 # API never mutates the submitted scenario
    assert make_policy(sh).actor.out_features==15


def test_training_rejects_dynamic_trajectories_without_silently_discarding():
    from stratoq_demo.learning_presets import validate_learning_scenario
    sc=preset_scenario(12).model_dump(mode='json')
    sc['balloons'][0]['trajectory_id']='original-trajectory'
    with pytest.raises(ValueError,match='remove attached HAP trajectories'):
        validate_learning_scenario(sc,12)


def test_curriculum_toggle_and_custom_stage_parameters():
    schedules={f'd{i}':[2.,1.] for i in range(5)}
    rng=np.random.default_rng(9)
    for episode in range(1,11):
        sched,n=learning_worker.curriculum_schedule(schedules,episode,10,rng,enabled=False)
        assert n==5 and sched==schedules
    for ep,expected in [(1,2),(4,2),(5,4),(8,4),(9,5),(10,5)]:
        sched,n=learning_worker.curriculum_schedule(schedules,ep,10,rng,
                 first_demands=2,second_demands=4,first_end_pct=40,second_end_pct=80)
        assert n==expected
        assert sum(any(val for val in v) for v in sched.values())==expected


def test_slot_progress_is_real_and_observation_masks_inactive_demands(monkeypatch):
    sc=preset_scenario(12);physical=synthetic_physical(sc)
    _,all_rates,storage=learning_worker.base_rates_and_storage(sc,physical)
    def fake_solve(paths,rates,buffers,max_storage,duration,gp=None):
        served={p.demand_id:min(p.requested_bps,2000) for p in paths}
        return served,{}, {},set(),buffers.copy(),sum(served.values())*duration
    monkeypatch.setattr(learning_worker,'solve_slot',fake_solve)
    def fake_base(actual,rates,buffers,max_storage,duration,algorithm,seed,n_samples=1,gp=None):
        return [],fake_solve([],rates,buffers,max_storage,duration)
    monkeypatch.setattr(learning_worker,'select_and_solve_slot',fake_base)
    schedule=learning_worker.rate_schedule(sc,12,300)
    schedule[sc.demands[-1].id]=[0.]*12
    _,_,_,mask=learning_worker.slot_inputs(sc,physical,all_rates[0],storage,schedule,0)
    assert not mask[:,len(sc.demands)].any() and mask[:,0].all()
    seen=[]
    out=learning_worker.run_episode(make_policy(topology_shape(sc)),sc,physical,all_rates,
          storage,None,schedule,demand_indices(sc),training=True,progress=seen.append)
    assert len(seen)==12 and seen[0]['slots_done']==1
    assert seen[-1]['slots_done']==12
    assert seen[-1]['slots_total']==12
    assert np.isclose(seen[-1]['partial_satisfaction'],out['satisfaction'])
    assert np.isclose(seen[-1]['partial_reward'],out['reward'])


def test_learning_api_accepts_custom_scenario_params_and_live_endpoint(monkeypatch,tmp_path):
    import main
    from stratoq_demo import learning_jobs
    sc=preset_scenario(12).model_dump(mode='json')
    monkeypatch.setattr(learning_jobs,'ROOT',tmp_path)
    # No subprocess: confirm the endpoint serializes a validated fixed scenario.
    received=[]
    monkeypatch.setattr(learning_jobs,'launch',lambda cfg:received.append(cfg) or {'id':'test','status':'queued'})
    req=main.LearningStart(scenario=sc,slots=24,episodes=2,
       curriculum_enabled=False,learning_rate=.0003,ppo_epochs=4)
    result=main.create_learning_run(req)
    assert result['status']=='queued' and received[0]['scenario']['config']['slots']==24
    assert received[0]['learning_rate']==.0003
    assert received[0]['curriculum_enabled'] is False
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        main.create_learning_run(main.LearningStart(scenario=sc,learning_rate=.4))
    jid='a'*32
    directory=tmp_path/jid;directory.mkdir()
    learning_worker.write_json(directory/'config.json',{'episodes':2})
    learning_worker.write_json(directory/'live.json',{'stage':'training','episode':1,'slots_done':3,'slots_total':12})
    assert main.learning_run_live(jid)['slots_done']==3


def test_custom_size_complete_training_streams_and_persists_snapshot(monkeypatch,tmp_path):
    """Real PPO weights and topology validation; synthetic physics/LP are test-only."""
    import json
    from stratoq_demo.learning_presets import PRESET
    sc=preset_scenario(12).model_dump(mode='json')
    sc['ground_stations'].append({'id':'gs-extra','name':'Extra','lat':49.1,'lon':-81.2})
    sc['balloons'].append({'id':'hap-extra','name':'Extra HAP','lat':49.0,'lon':-81.05})
    sc['demands'].append({'id':'d-extra','source':'gs-extra','target':'gs-timmins','rate_bps':1500})
    class FakeModel:
        def __init__(self,*a,**k):pass
        Params=SimpleNamespace(OutputFlag=0)
        def addVar(self,**kwargs):return None
        def optimize(self):return None
        def dispose(self):return None
    monkeypatch.setattr(learning_worker,'require_gurobi',lambda:SimpleNamespace(Model=FakeModel))
    monkeypatch.setattr(learning_worker,'create_physical_network',lambda sc,progress=None:synthetic_physical(sc))
    def fake_solve(paths,rates,buffers,max_storage,duration,gp=None):
        served={p.demand_id:min(2500,p.requested_bps) for p in paths}
        return served,{},{},set(lid for p in paths for lid in (p.uplink_id,p.downlink_id)),buffers.copy(),sum(served.values())*duration
    def fake_reference(actual,rates,buffers,max_storage,duration,algorithm,seed,n_samples=1,gp=None):
        return [],fake_solve([],rates,buffers,max_storage,duration)
    monkeypatch.setattr(learning_worker,'solve_slot',fake_solve)
    monkeypatch.setattr(learning_worker,'select_and_solve_slot',fake_reference)
    job=tmp_path/'test-job';job.mkdir()
    learning_worker.write_json(job/'config.json',{'preset':PRESET,'scenario':sc,'slots':12,
        'episodes':2,'checkpoint_every':1,'seed':17,'curriculum_enabled':False,
        'learning_rate':.0003,'ppo_epochs':2,'batch_size':8,'entropy_start':.008,'entropy_end':.002})
    learning_worker.train(job)
    status=json.loads((job/'status.json').read_text())
    shape=json.loads((job/'topology.json').read_text())['shape']
    live=json.loads((job/'live.json').read_text())
    metrics=json.loads((job/'metrics.json').read_text())
    assert status['status']=='complete'
    assert len(status['checkpoints'])==3
    assert (shape['n_gs'],shape['n_haps'],shape['n_demands'])==(4,3,4)
    assert len(metrics)==2 and all(m['active_demands']==4 for m in metrics)
    assert abs(metrics[-1]['entropy_coef']-.002)<1e-8
    assert live['episode_complete'] and live['slots_done']==12
    assert (job/'evaluation_000002.json').exists()
