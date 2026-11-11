"""v133: configurable reward constants, API persistence, update diagnostics.

The paper's original formula remains the default; the server and worker must
never silently ignore the configured constants. Synthetic data is TEST ONLY.
"""
import pytest
from fastapi import HTTPException
from main import LearningStart, create_learning_run
from stratoq_demo.learning_core import RewardShape, paper_shaped_reward, validate_reward_shape
from stratoq_demo.learning_presets import preset_scenario
from stratoq_demo import learning_jobs


def _score(rho, hi=.7, lo=.5, shape=None):
    return paper_shaped_reward({'d':rho*100}, {'d':hi*100}, {'d':lo*100},
                               {'d':100}, shape)


def test_reward_paper_values_exact_when_unchanged():
    assert _score(.95) == 1
    assert _score(.70) == pytest.approx(.6)
    assert _score(.8) == pytest.approx(.6+.4*.1)
    assert _score(.6) == pytest.approx(.1+.1*(.6-.5)/(.7-.5+1e-10),abs=1e-8)
    assert _score(.4) == pytest.approx(-.1)
    original=RewardShape()
    assert _score(.91,shape=original) == pytest.approx(_score(.91))
    assert _score(.94,shape=vars(original)) == pytest.approx(_score(.94))
    assert _score(.7)-_score(.7-1e-7) > .39  # important reward discontinuity
    # The source equation gives a positive reward even when *nothing* is served.
    assert _score(0,hi=0,lo=0)==pytest.approx(.6)
    assert _score(0,hi=0,lo=0,shape=RewardShape(reward_zero_service_guard=True))==0.


def test_independent_constants_modify_only_corresponding_piece():
    changed=RewardShape(reward_success_threshold=.99, reward_success=.8,
            reward_at_or_above_hi=.25, reward_above_hi_slope=1.3,
            reward_between_base=.05, reward_between_gain=.2,
            reward_below_slope=2)
    assert _score(1,shape=changed)==pytest.approx(.8)
    assert _score(.80,shape=changed)==pytest.approx(.25+1.3*.1)
    assert _score(.60,shape=changed)==pytest.approx(.05+.2*.5,abs=1e-8)
    assert _score(.40,shape=changed)==pytest.approx(-.2)
    assert _score(.70,shape=changed)==pytest.approx(.25)
    assert _score(.70-1e-7,shape=changed)==pytest.approx(.25,abs=1e-5)


@pytest.mark.parametrize('key,value',[
    ('reward_success_threshold',-0.1),('reward_success_threshold',1.1),
    ('reward_success',float('nan')),('reward_at_or_above_hi',-1),
    ('reward_above_hi_slope',5.1),('reward_between_gain',3),
    ('reward_below_slope',float('inf')),
])
def test_invalid_rewards_are_rejected(key,value):
    with pytest.raises(ValueError):validate_reward_shape({key:value})


def test_api_forwards_exact_shape_to_new_worker_job(monkeypatch):
    received=[]
    monkeypatch.setattr(learning_jobs,'launch',lambda data:received.append(data) or {'id':'test','status':'queued'})
    config=LearningStart(scenario=preset_scenario(12).model_dump(mode='json'),
             slots=12,episodes=2,reward_success_threshold=.98,
             reward_success=.8,reward_at_or_above_hi=.25,
             reward_above_hi_slope=1.3,reward_between_base=.05,
             reward_between_gain=.2,reward_below_slope=2.)
    assert create_learning_run(config)['status']=='queued'
    assert validate_reward_shape(received[0])==validate_reward_shape(config.model_dump())
    for field in vars(RewardShape()):
        assert field in received[0]
    for field in vars(RewardShape()):
        if field=='reward_zero_service_guard':continue
        bad=LearningStart.model_validate({field:-1})
        with pytest.raises(HTTPException):
            create_learning_run(bad)


def test_training_episode_applies_reward_shape_not_just_api(monkeypatch):
    from stratoq_demo import learning_worker as worker
    from stratoq_demo.learning_core import demand_indices, make_policy, topology_shape
    from test_learning_lab import synthetic_physical
    sc=preset_scenario(12)
    physics=synthetic_physical(sc)
    _, rates, storage=worker.base_rates_and_storage(sc,physics)
    def choose(*a,**kw):
        return [1,0],0.,0.
    def solve(paths,lr,buffers,caps,duration,gp=None):
        served={p.demand_id:p.requested_bps*.8 for p in paths}
        return served,{}, {},set(),buffers.copy(),sum(served.values())*duration
    def baseline(actual,lr,buffers,caps,duration,algorithm,seed,n_samples=1,gp=None):
        # Both baselines serve 70% of only the first demand.
        first=actual.demands[0]
        return [],({first.id:first.rate_bps*.7},{},{},set(),buffers.copy(),first.rate_bps*.7*duration)
    monkeypatch.setattr(worker,'sample_choices',choose)
    monkeypatch.setattr(worker,'solve_slot',solve)
    monkeypatch.setattr(worker,'select_and_solve_slot',baseline)
    schedule=worker.rate_schedule(sc,12,sc.config.slot_seconds)
    policy=make_policy(topology_shape(sc))
    kwargs=dict(training=True,rng_seed=9)
    before=worker.run_episode(policy,sc,physics,rates,storage,None,
                              schedule,demand_indices(sc),**kwargs)
    adjusted=worker.run_episode(policy,sc,physics,rates,storage,None,
                              schedule,demand_indices(sc),
                              reward_shape=RewardShape(reward_at_or_above_hi=.25),**kwargs)
    assert adjusted['satisfaction']==pytest.approx(before['satisfaction'])
    # All THREE demands previously receive the positive match-best bonus,
    # including the two with zero service from both agent and heuristics.
    assert before['reward']-adjusted['reward']==pytest.approx(.6-.25)
    guarded=worker.run_episode(policy,sc,physics,rates,storage,None,
                               schedule,demand_indices(sc),
                               reward_shape=RewardShape(reward_at_or_above_hi=.25,
                                                        reward_zero_service_guard=True),**kwargs)
    assert guarded['reward']==pytest.approx(adjusted['reward']-2*.25/3)


def test_ppo_diagnostics_report_finite_weight_movement():
    import numpy as np
    import torch
    from stratoq_demo.learning_core import (demand_indices, make_policy,
            topology_shape, sample_choices, ppo_update)
    scenario=preset_scenario(12)
    shape=topology_shape(scenario)
    policy=make_policy(shape)
    optimizer=torch.optim.Adam(policy.parameters(),lr=.001)
    obs=np.zeros(shape.observation_dim,dtype=np.float32)
    mask=np.ones((shape.n_haps,shape.n_demands+1),dtype=bool)
    ports=demand_indices(scenario)
    records=[]
    torch.manual_seed(21)
    for step in range(8):
        actions,lp,v=sample_choices(policy,obs,mask,ports)
        records.append(dict(obs=obs,mask=mask,choices=actions,
                            logp=lp,value=v,reward=step*.07))
    stats=ppo_update(policy,optimizer,records,ports,ppo_epochs=2)
    assert all(np.isfinite(x) for x in stats.values())
    assert stats['relative_weight_change']>0
    assert stats['approx_kl']>=-1e-5
    assert 0<=stats['clip_fraction']<=1
