"""Persistent subprocess manager: a PPO job survives browser reloads.

Training never blocks FastAPI's request thread. The worker writes atomic JSON
status/metric/evaluation files; the parent serves them read-only.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import sys
import uuid
from threading import Lock
from .learning_presets import PRESET, preset_metadata
from .learning_worker import write_json

ROOT=Path(__file__).resolve().parent.parent/'data'/'learning'
_LOCK=Lock()
_CHILDREN={}
_VALID=re.compile(r'^[0-9a-f]{32}$')


def job_dir(job_id):
    if not _VALID.fullmatch(job_id):raise ValueError('Invalid learning job identifier')
    return ROOT/job_id


def _load_json(path,default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (FileNotFoundError,ValueError,UnicodeDecodeError):return default


def get(job_id):
    path=job_dir(job_id)
    state=_load_json(path/'status.json')
    if state is None:return None
    if state['status'] in ('queued','running'):
        with _LOCK:child=_CHILDREN.get(job_id)
        exited=child is not None and child.poll() is not None
        # A backend restart forgets the Popen handle, not the worker process.
        # Do not leave an orphaned "running" badge indefinitely if its PID died.
        if child is None and (path/'pid').exists():
            pid=(path/'pid').read_text().strip()
            if pid.isdecimal():
                try: os.kill(int(pid),0)
                except ProcessLookupError:exited=True
                except PermissionError:pass
        if exited:
            # Worker should write a detailed failure; detect abrupt kill as well.
            reread=_load_json(path/'status.json')
            if reread and reread['status'] not in ('queued','running'):return reread
            state.update(status='failed',stage='failed',error='Learning worker exited unexpectedly. Inspect run.log.')
            write_json(path/'status.json',state)
    return state


def launch(config):
    with _LOCK:
        ROOT.mkdir(parents=True,exist_ok=True)
        for candidate in sorted(ROOT.iterdir()):
            if not candidate.is_dir() or not _VALID.fullmatch(candidate.name):continue
            state=_load_json(candidate/'status.json',{})
            if state.get('status') in ('queued','running'):
                child=_CHILDREN.get(candidate.name)
                if child is not None and child.poll() is None:
                    raise ValueError(f'Learning run {candidate.name[:8]} is already active; stop it first.')
                # A job created before backend restart may still be running.
                pid=(candidate/'pid').read_text().strip() if (candidate/'pid').exists() else ''
                if pid.isdecimal():
                    try:os.kill(int(pid),0)
                    except ProcessLookupError:pass
                    except PermissionError:raise ValueError('An existing learning worker is still active.')
                    else:raise ValueError('An existing learning worker is still active.')
        jid=uuid.uuid4().hex
        path=job_dir(jid);path.mkdir(parents=True,exist_ok=False)
        data=dict(config)
        write_json(path/'config.json',data)
        write_json(path/'status.json',{'id':jid,'status':'queued','stage':'queued',
            'episode':0,'episodes':data['episodes'],'checkpoints':[],'error':None})
        with (path/'run.log').open('ab') as out:
            proc=subprocess.Popen([sys.executable,'-m','stratoq_demo.learning_worker',
                                   '--job-dir',str(path)],cwd=str(ROOT.parent.parent),
                                  stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        (path/'pid').write_text(str(proc.pid))
        _CHILDREN[jid]=proc
    return get(jid)


def latest():
    if not ROOT.is_dir():return None
    folders=[d for d in ROOT.iterdir() if d.is_dir() and _VALID.fullmatch(d.name)]
    if not folders:return None
    newest=max(folders,key=lambda d:d.stat().st_mtime)
    return get(newest.name)


def _compact_records(rows, max_points):
    """Preserve endpoints and local reward/satisfaction extrema in chart previews.

    Full measurements remain in metrics.jsonl; max_points only affects the
    response, never the experiment data or the actual PPO calculations.
    """
    if not max_points or len(rows) <= max_points:return rows
    if max_points == 1:return [rows[-1]]
    if max_points < 6:return [rows[0],rows[-1]]
    # Deterministic min/max per chronological bucket, preserving spikes and
    # drops rather than flattening the curve through averaging.
    interior=rows[1:-1]
    n_buckets=max(1,(max_points-2)//6)
    collected={0:rows[0],len(rows)-1:rows[-1]}
    for k in range(n_buckets):
        lo=1+(k*len(interior))//n_buckets
        hi=1+((k+1)*len(interior))//n_buckets
        if hi<=lo:continue
        bucket=rows[lo:hi]
        collected[lo]=rows[lo]
        collected[hi-1]=rows[hi-1]
        for field in ('train_reward','train_satisfaction'):
            finite=[(j,v.get(field)) for j,v in enumerate(bucket)
                    if isinstance(v.get(field),(int,float))]
            if finite:
                imin=min(finite,key=lambda entry:entry[1])[0]
                imax=max(finite,key=lambda entry:entry[1])[0]
                collected[lo+imin]=rows[lo+imin]
                collected[lo+imax]=rows[lo+imax]
    return [collected[i] for i in sorted(collected)]


def metrics(job_id, since=0, max_points=0):
    """Fetch records with episode > since; old JSON runs remain readable."""
    path=job_dir(job_id)
    if not (path/'config.json').exists():return None
    stream=path/'metrics.jsonl'
    offsets=path/'metrics.offsets'
    if stream.exists() and offsets.exists():
        rows=[]
        # Each 8-byte index record references a complete, published metric.
        with offsets.open('rb') as index,stream.open('rb') as data:
            count=offsets.stat().st_size//8
            index.seek(min(max(0,int(since)),count)*8)
            for _ in range(max(0,count-max(0,int(since)))):
                record=index.read(8)
                if len(record)!=8:break
                (byte_offset,)=struct.unpack('<Q',record)
                data.seek(byte_offset)
                raw=data.readline()
                try:rows.append(json.loads(raw))
                except (ValueError,UnicodeDecodeError):break
        return _compact_records(rows,max_points)
    old=_load_json(path/'metrics.json',[])
    return _compact_records([v for v in old if v.get('episode',0)>since],max_points)


def evaluation(job_id,episode):
    path=job_dir(job_id)
    if not (path/'config.json').exists():return None
    state=get(job_id)
    if state is None or episode not in [c['episode'] for c in state.get('checkpoints',[])]:return None
    return _load_json(path/f'evaluation_{episode:06d}.json')


def stop(job_id):
    path=job_dir(job_id)
    state=get(job_id)
    if state is None:return None
    if state.get('status') not in ('queued','running'):return state
    with _LOCK:
        proc=_CHILDREN.get(job_id)
        if proc is not None and proc.poll() is None:
            try:os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        else:
            # Do not kill arbitrary PIDs of processes from a previous server.
            raise ValueError('This job belongs to another backend session; stop its process manually.')
    state.update(status='stopped',stage='stopped',error=None)
    write_json(path/'status.json',state)
    return state


def live(job_id):
    path=job_dir(job_id)
    if not (path/'config.json').exists():return None
    return _load_json(path/'live.json',{})
