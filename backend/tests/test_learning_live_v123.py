"""Regression coverage for live progress, time grid, and curriculum-off POST.
Scientific rate/LP computations are NOT mocked in production code.
"""
from __future__ import annotations
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from stratoq_demo.learning_presets import preset_scenario, validate_learning_scenario, validate_time_grid
from stratoq_demo.learning_core import topology_shape
from stratoq_demo import learning_worker


def test_slot_length_and_horizon_preserve_topology_shape():
    src=preset_scenario().model_dump(mode='json')
    original=topology_shape(preset_scenario())
    for slots,seconds in ((6,10),(24,300),(48,150),(288,300),(1,3600)):
        sc=validate_learning_scenario(src,slots,seconds)
        assert sc.config.slots==slots
        assert sc.config.slot_seconds==seconds
        assert topology_shape(sc)==original
        assert src['config']['slot_seconds']==300
    for slots,seconds in ((0,300),(289,300),(25,3600),(12,0),(12,3601)):
        with pytest.raises(ValueError): validate_time_grid(slots,seconds)


def test_no_curriculum_uses_full_active_demand_count():
    schedule={f'd{i}':[1.,2.,3.] for i in range(5)}
    import numpy as np
    for ep in (1,3,20):
        actual,n=learning_worker.curriculum_schedule(schedule,ep,20,np.random.default_rng(13),enabled=False)
        assert actual==schedule and n==5


def test_http_post_curriculum_off_and_time_grid(monkeypatch, tmp_path):
    import main
    from stratoq_demo import learning_jobs
    received=[]
    monkeypatch.setattr(learning_jobs,'launch',lambda cfg:received.append(cfg) or {'id':'a'*32,'status':'queued'})
    with TestClient(main.app) as client:
        sc=preset_scenario().model_dump(mode='json')
        result=client.post('/api/learning/runs',json={
            'preset':'ontario-compact-v1','scenario':sc,
            'slots':30,'slot_seconds':120, 'episodes':2,
            'curriculum_enabled':False,'compare_baselines':False})
        assert result.status_code==202, result.json()
        assert received[0]['curriculum_enabled'] is False
        assert received[0]['compare_baselines'] is False
        assert received[0]['scenario']['config']['slots']==30
        assert received[0]['scenario']['config']['slot_seconds']==120
        broken=client.post('/api/learning/runs',json={'slots':25,'slot_seconds':3600})
        assert broken.status_code==400
        broken=client.post('/api/learning/runs',json={'slot_seconds':'banana'})
        assert broken.status_code==422
        assert broken.json()['detail'][0]['loc']==['body','slot_seconds']
        preset=client.get('/api/learning/preset?slots=10&slot_seconds=60')
        assert preset.status_code==200
        assert preset.json()['horizon_seconds']==600


def test_final_live_progress_and_worker_finish(monkeypatch,tmp_path):
    """Every request is a real job state; native allocation mocked only in test."""
    import torch
    from stratoq_demo.learning_presets import PRESET
    from test_learning_lab import synthetic_physical
    class FakeModel:
        def __init__(self,*args,**kwargs): pass
        Params=SimpleNamespace(OutputFlag=0)
        def addVar(self,**kwargs):return None
        def optimize(self):return None
        def dispose(self):return None
    monkeypatch.setattr(learning_worker,'require_gurobi',lambda:SimpleNamespace(Model=FakeModel))
    monkeypatch.setattr(learning_worker,'create_physical_network',lambda scenario,progress=None:synthetic_physical(scenario))
    saw={'live':False,'first_eval':False,'training_stream':False,'episodes':set()}
    original_write=learning_worker.write_json
    def spying_write(path,value):
        if str(path).endswith('live.json'):
            if value.get('stage')=='initial-evaluation' and value.get('slots_done')==1: saw['first_eval']=True
            if value.get('stage')=='training' and value.get('slots_done')==1: saw['training_stream']=True
        if str(path).endswith('metrics.json'): saw['episodes'].add(len(value))
        return original_write(path,value)
    monkeypatch.setattr(learning_worker,'write_json',spying_write)
    def fake_solve(paths,rates,buffers,max_storage,duration,gp=None):
        served={p.demand_id:min(p.requested_bps,2500.) for p in paths}
        return served,{},{},set(),buffers.copy(),sum(served.values())*duration
    monkeypatch.setattr(learning_worker,'solve_slot',fake_solve)
    def no_baseline(*args,**kwargs):
        raise AssertionError('Baselines should not run unless enabled')
    def fake_heur(actual,rates,buffers,max_storage,duration,algorithm,seed,n_samples=1,gp=None):
        return [],fake_solve([],rates,buffers,max_storage,duration)
    monkeypatch.setattr(learning_worker,'select_and_solve_slot',fake_heur)
    monkeypatch.setattr(learning_worker,'evaluate_baseline',no_baseline)
    job=tmp_path/'job';job.mkdir()
    original_write(job/'config.json',{'preset':PRESET,'slots':12,'slot_seconds':300,'episodes':2,
        'checkpoint_every':1,'seed':42,'curriculum_enabled':False,'compare_baselines':False})
    learning_worker.train(job)
    state=json.loads((job/'status.json').read_text())
    metric=json.loads((job/'metrics.json').read_text())
    live=json.loads((job/'live.json').read_text())
    assert state['status']=='complete' and state['stage']=='complete' and state['episode']==2
    assert live['stage']=='complete' and live['episode_complete'] is True
    assert saw['first_eval'] and saw['training_stream']
    assert saw['episodes']=={1,2}
    assert all(m['active_demands']==3 for m in metric)
    assert [c['episode'] for c in state['checkpoints']]==[0,1,2]
