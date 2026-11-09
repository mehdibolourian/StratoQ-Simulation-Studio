"""v1.2.4 regression: unlimited positive episodes, append-only metrics and bounds.
No production optical rates or policy actions are replaced.
"""
from __future__ import annotations
import json
from pathlib import Path
import uuid
from fastapi.testclient import TestClient
from stratoq_demo.learning_presets import preset_scenario
from stratoq_demo import learning_jobs, learning_worker


def test_learning_request_accepts_long_episode_counts(monkeypatch):
    import main
    observed=[]
    monkeypatch.setattr(learning_jobs,'launch',lambda data: observed.append(data) or {'status':'queued','id':'a'*32})
    scenario=preset_scenario().model_dump(mode='json')
    with TestClient(main.app) as api:
        res=api.post('/api/learning/runs',json={'scenario':scenario,'episodes':100000,
                'checkpoint_every':2500,'curriculum_enabled':False})
        assert res.status_code==202,res.text
        assert observed[-1]['episodes']==100000
        assert observed[-1]['checkpoint_every']==2500
        assert api.post('/api/learning/runs',json={'scenario':scenario,'episodes':0}).status_code==400
        assert api.post('/api/learning/runs',json={'scenario':scenario,'checkpoint_every':0}).status_code==400


def test_metric_stream_supports_incremental_reads_without_quadratic_json(monkeypatch,tmp_path):
    monkeypatch.setattr(learning_jobs,'ROOT',tmp_path)
    job_id=uuid.uuid4().hex
    directory=tmp_path/job_id
    directory.mkdir()
    (directory/'config.json').write_text('{}')
    for ep in range(1,3501):
        learning_worker.append_metric(directory, {'episode':ep,'train_reward':((ep*13)%113)/100,
            'train_satisfaction':((ep*7)%89)/100,'policy_loss':-ep*.0001})
    assert len(learning_jobs.metrics(job_id))==3500
    latest=learning_jobs.metrics(job_id,since=3497)
    assert [p['episode'] for p in latest]==[3498,3499,3500]
    short=learning_jobs.metrics(job_id,max_points=1800)
    assert len(short)<=1800
    assert short[0]['episode']==1 and short[-1]['episode']==3500
    # Checking an earlier interval doesn't affect the newly appended data.
    assert learning_jobs.metrics(job_id,since=3500)==[]
    learning_worker.append_metric(directory,{'episode':3501,'train_reward':.8,'train_satisfaction':.6})
    assert learning_jobs.metrics(job_id,since=3500)[0]['episode']==3501


def test_metric_endpoint_limits_payload_and_returns_only_new_rows(monkeypatch,tmp_path):
    import main
    monkeypatch.setattr(learning_jobs,'ROOT',tmp_path)
    job_id=uuid.uuid4().hex; directory=tmp_path/job_id; directory.mkdir()
    (directory/'config.json').write_text('{}')
    for ep in range(1,101):
        learning_worker.append_metric(directory,{'episode':ep,'train_reward':ep/100,'train_satisfaction':ep/100})
    with TestClient(main.app) as api:
        r=api.get(f'/api/learning/runs/{job_id}/metrics?since=97&max_points=1800')
        assert r.status_code==200
        assert [v['episode'] for v in r.json()]==[98,99,100]
        assert api.get(f'/api/learning/runs/{job_id}/metrics?since=-1').status_code==400
