"""Small in-process progress manager for expensive physical channel jobs.

Process-local on purpose: run Uvicorn with one worker. Auto-reload restarts
pending jobs, which is reported to the user instead of returning fake results.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Lock
import logging
import time
import traceback
import uuid
from .stratoq_adapter import simulate

LOGGER = logging.getLogger('uvicorn.error')
_POOL=ThreadPoolExecutor(max_workers=2, thread_name_prefix='stratoq-simulation')
_LOCK=Lock()
_JOBS={}

@dataclass
class Job:
    id: str
    status: str = 'queued'
    stage: str = 'queued'
    total: int = 0
    completed: int = 0
    cached: int = 0
    computed: int = 0
    workers: int = 0
    created_at: float = field(default_factory=time.time)
    elapsed_seconds: float = 0.
    error: str | None = None
    result: object = None

    def snapshot(self):
        return {k:getattr(self,k) for k in ('id','status','stage','total','completed',
                  'cached','computed','workers','elapsed_seconds','error')}


def launch(scenario):
    jid=uuid.uuid4().hex
    job=Job(jid)
    with _LOCK:
        # Prune old completed records, preserving active jobs.
        done=sorted((j for j in _JOBS.values() if j.status in ('complete','failed')),key=lambda j:j.created_at)
        for old in done[:-15]: _JOBS.pop(old.id,None)
        _JOBS[jid]=job
    _POOL.submit(_run,job,scenario)
    return job.snapshot()


def _run(job,scenario):
    started=time.perf_counter()
    with _LOCK:
        job.status='running';job.stage='setup'
    LOGGER.info('[StratoQ %s] setup for %d GS, %d HAP, %d slots; upstream balloon_qnet theory',
                job.id[:8],len(scenario.ground_stations),len(scenario.balloons),scenario.config.slots)
    def progress(update):
        with _LOCK:
            for name,value in update.items():
                if hasattr(job,name):setattr(job,name,value)
            job.elapsed_seconds=round(time.perf_counter()-started,2)
    try:
        result=simulate(scenario,progress=progress)
        with _LOCK:
            job.result=result;job.stage='complete';job.status='complete'
            job.elapsed_seconds=round(time.perf_counter()-started,2)
        LOGGER.info('[StratoQ %s] complete in %.2fs; new=%d, cached=%d',
                    job.id[:8],job.elapsed_seconds,job.computed,job.cached)
    except Exception as exc:
        LOGGER.error('[StratoQ %s] physics failed: %s\n%s',job.id[:8],exc,traceback.format_exc())
        with _LOCK:
            job.status='failed';job.stage='failed';job.error=f'{type(exc).__name__}: {exc}'
            job.elapsed_seconds=round(time.perf_counter()-started,2)


def get(jid):
    with _LOCK:
        job=_JOBS.get(jid)
        return job.snapshot() if job else None


def get_result(jid):
    with _LOCK:
        job=_JOBS.get(jid)
        return job.result if job and job.status=='complete' else None
