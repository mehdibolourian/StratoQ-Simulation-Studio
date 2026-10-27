"""Prevent accidental duplicate / parallel CDS requests. No network calls."""
import os
import sys
import types
from datetime import date
import pytest
from fastapi.testclient import TestClient
from main import app
from stratoq_demo.setup import default_scenario
from stratoq_demo import era5_jobs as jobs


class FakeExecutor:
    def __init__(self):
        self.submissions=[]
    def submit(self, fn, *args):
        self.submissions.append((fn,args))


@pytest.fixture
def isolate(monkeypatch,tmp_path):
    monkeypatch.setattr(jobs,'_JOBS',{})
    monkeypatch.setattr(jobs,'JOBS_DIR',tmp_path/'jobs')
    monkeypatch.setattr(jobs,'CDS_COOLDOWN_PATH',tmp_path/'cooldown.json')
    mock=FakeExecutor()
    monkeypatch.setattr(jobs,'_POOL',mock)
    return mock,tmp_path


def test_single_flight_deduplicates_and_rejects_other_date(isolate):
    executor,_=isolate
    scenario=default_scenario()
    first=jobs.launch('2025-01-23',scenario)
    identical=jobs.launch('2025-01-23',scenario)
    assert identical['id']==first['id']
    assert len(executor.submissions)==1
    with pytest.raises(jobs.ERA5BusyError,match='already active'):
        jobs.launch('2025-01-24',scenario)
    assert len(executor.submissions)==1
    jobs._set(first['id'], status='complete')
    second=jobs.launch('2025-01-24',scenario)
    assert second['id']!=first['id']
    assert len(executor.submissions)==2


def test_legacy_cds_module_refuses_parallel_requests(isolate):
    executor,_=isolate
    scenario=default_scenario()
    jobs.launch('2025-01-23',scenario)
    with pytest.raises(jobs.ERA5BusyError):
        jobs.launch('2025-01-24',scenario)
    assert len(executor.submissions)==1


def test_cds_rejected_queue_cooldown_does_not_auto_resubmit(isolate,monkeypatch):
    executor,tmp_path=isolate
    monkeypatch.setattr(jobs.Path,'home',classmethod(lambda cls:tmp_path))
    (tmp_path/'.cdsapirc').write_text('fixture')
    monkeypatch.setattr(jobs,'PARTS_DIR',tmp_path/'daily')
    class RejectedCDSClient:
        def __init__(self,**kwargs):pass
        def retrieve(self,*args):
            raise RuntimeError('The job has been rejected Maximum number queued requests for this dataset has been reached. Please configure your scripts to request data sequentially')
    monkeypatch.setitem(sys.modules,'cdsapi',types.SimpleNamespace(Client=RejectedCDSClient))
    scenario=default_scenario()
    first=jobs.launch('2025-01-23',scenario)
    assert len(executor.submissions)==1
    executor.submissions[0][0](*executor.submissions[0][1])
    outcome=jobs.status(first['id'])
    assert outcome['status']=='failed'
    assert outcome['phase']=='cds-quota'
    assert 'queue limit' in outcome['error']
    assert jobs._queue_pause_remaining()>0
    assert len(executor.submissions)==1
    # Simulates reboot while cooldown still applies.
    jobs._JOBS.clear()
    assert jobs._queue_pause_remaining()>0
    with pytest.raises(jobs.ERA5QueueLimitError):
        jobs.launch('2025-01-24',scenario)
