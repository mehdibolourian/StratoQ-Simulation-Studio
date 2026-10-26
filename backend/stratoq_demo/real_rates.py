"""Exact upstream balloon_qnet theoretical-channel evaluations with per-point disk cache.

The physics is transmittance_simulation.channel_theory (LOWTRAN7, turbulence,
AO, SMF coupling and detector losses), not the Studio gaussian approximation.
Only the user-defined weather overlay is additional to the upstream model.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import sqlite3
import threading
import time

# LOWTRAN7's compiled Fortran module contains shared state. Do not execute
# the native routine simultaneously in multiple worker threads.
LOWTRAN_LOCK = threading.Lock()
LOGGER=logging.getLogger("uvicorn.error")
CACHE_VERSION = 'balloon_qnet-upstream-theory-v1'
# Also invalidate the cache when source physics formulas change.
_SOURCE_ROOT = Path(__file__).resolve().parent.parent / 'balloon_qnet'
_SOURCE_FILES = ('free_space_losses.py', 'transmittance.py', 'smf_coupling.py',
                 'cn2.py', 'transmittance_simulation.py',
                 'lowtran_piccia/fortran/lowtran7.f')
_src_hasher = hashlib.sha256()
for _name in _SOURCE_FILES:
    _src_hasher.update((_SOURCE_ROOT / _name).read_bytes())
PHYSICS_SOURCE_HASH = _src_hasher.hexdigest()[:16]
CACHE_PATH = Path(os.environ.get('STRATOQ_RATE_CACHE', str(Path(__file__).resolve().parent.parent / '.rate-cache.sqlite3')))


def optical_args(optical):
    return {
        'wavelength': optical.wavelength_nm * 1e-9,
        'W0': optical.beam_waist_m,
        'rx_aperture_down': optical.rx_aperture_down_m,
        'rx_aperture_up': optical.rx_aperture_up_m,
        'obs_ratio': optical.obscuration_ratio,
        'Cn0': optical.cn0,
        'u_rms': optical.wind_speed_mps,
        'pointing_error': optical.pointing_error_rad,
        'tracking_efficiency': optical.tracking_efficiency,
        'detector_eff': optical.detector_efficiency,
        'init_time': 1,
    }


def point_key(direction, distance_km, altitude_km, params, ao_order):
    """Complete calculation fingerprint; independent of array index and node names.

    Distances are rounded to 9 decimals (micrometre resolution in km), to
    remove insignificant float jitter while never reusing visibly changed links.
    """
    payload = {'model': CACHE_VERSION, 'source_hash': PHYSICS_SOURCE_HASH, 'direction': direction,
               'distance_km': round(float(distance_km), 9),
               'altitude_km': round(float(altitude_km), 9),
               'ao_order': int(ao_order), 'params': params}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()


def _connect():
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(CACHE_PATH), timeout=60)
    db.execute('CREATE TABLE IF NOT EXISTS efficiencies (key TEXT PRIMARY KEY, eta REAL NOT NULL)')
    return db


def evaluate_theoretical_point(task):
    """Invoke the actual upstream physics. No silent approximation/fallback."""
    direction, distance_km, altitude_km, params, ao_order = task
    from balloon_qnet import transmittance_simulation as ts
    # Channel construction is independent per thread; only LOWTRAN's native
    # atmosphere routine must be serialized. Substitute *only the LOWTRAN
    # call*, never any atmosphere or optical approximation.
    # Serializing the entire method would erase parallelism. Instead, the
    # atmospheric code takes its lock inside transmittance.slant itself.
    try:
        eta = ts.channel_theory(direction=direction, gs_alt=0., hap_alt=altitude_km,
                                distance=distance_km, n_correction=ao_order,
                                params_in=params)
    except (ImportError, FileNotFoundError, OSError) as exc:
        raise RuntimeError(
            'Original balloon_qnet theoretical channel could not load LOWTRAN7. '
            'Install CMake, gfortran, and the Python physical-model dependencies '
            '(Python >=3.12 also needs meson + meson-python + ninja), '
            'then run python verify_physics.py. Original error: '
            +str(exc)) from exc
    eta = float(eta)
    if not math.isfinite(eta) or not 0 <= eta <= 1:
        raise ValueError(f'Upstream balloon_qnet returned invalid efficiency {eta!r} for {task[:3]}')
    return eta


def skr_bps(eta, optical):
    """Same BB84 equation as upstream ts.compute_skr, with UI source/QBER."""
    q = optical.qber
    entropy = -q * math.log2(q) - (1-q) * math.log2(1-q) if 0 < q < 1 else 0.
    return max(0., optical.source_rate_hz * optical.source_efficiency * eta * (1 - 2 * entropy))


def calculate_key_rate_mac_real(directed_links, physical, optical, progress=None,
                                max_workers=4, evaluator=None):
    """Calculate all directed K_MAX[t] using deduplicated, parallel upstream theory.

    Link-slot metadata is already produced from trajectory samples. Physical
    eta is cached persistently by geometry + optical params; user weather loss
    and manual link limits are applied afterwards (without re-running LOWTRAN).
    """
    if evaluator is None: evaluator = evaluate_theoretical_point
    params = optical_args(optical)
    tasks = {}
    entries = []
    for li, l in enumerate(directed_links):
        up = not hasattr(l.n1, 'H')
        h = l.n2 if up else l.n1
        g = l.n1 if up else l.n2
        direction = 'uplink' if up else 'downlink'
        history = physical.scene_links[(g.tag, h.tag)]
        for slot, record in enumerate(history):
            if (not record['enabled'] or not record['in_range'] or
                record['elevation_deg'] <= 0 or record['capacity_limit_bps'] == 0):
                entries.append((li, slot, None, record))
                continue
            dist = record['distance_km']; alt = h.H[slot]
            key = point_key(direction, dist, alt, params, optical.ao_correction_order)
            tasks[key] = (direction, dist, alt, params, optical.ao_correction_order)
            entries.append((li, slot, key, record))

    start=time.perf_counter()
    with _connect() as db:
        # Chunked IN so a large topology cannot exceed SQLite's parameter limit.
        cached = {}
        keys=list(tasks)
        for i in range(0,len(keys),500):
            batch=keys[i:i+500]
            if batch:
                cached.update(db.execute('SELECT key,eta FROM efficiencies WHERE key IN ('+
                              ','.join('?' for _ in batch)+')', batch).fetchall())
        missing={key:value for key,value in tasks.items() if key not in cached}
        count=len(tasks)
        info={'stage':'channel', 'total':count, 'completed':len(cached),
              'cached':len(cached), 'computed':0, 'workers':min(max_workers,len(missing)) if missing else 0}
        LOGGER.info('[StratoQ physics] unique=%d, cache hits=%d, to compute=%d, threads=%d',
                    count,len(cached),len(missing),info['workers'])
        if progress:progress(info.copy())
        if missing:
            with ThreadPoolExecutor(max_workers=max(1,min(max_workers,24))) as pool:
                futures={pool.submit(evaluator, task): key for key,task in missing.items()}
                try:
                    for future in as_completed(futures):
                        key=futures[future]
                        eta=future.result() # raise on real physical model failure
                        cached[key]=eta
                        db.execute('INSERT OR REPLACE INTO efficiencies VALUES (?,?)',(key,eta))
                        info['completed']+=1;info['computed']+=1
                        if info['computed']%10==0: db.commit()
                        if info['computed']%25 == 0 or info['completed']==count:
                            LOGGER.info('[StratoQ physics] %d/%d (%d cached, %d newly computed)',
                                        info['completed'],count,info['cached'],info['computed'])
                        if progress:progress(info.copy())
                finally:
                    db.commit() # don't lose successful results after an error
        rows=[[0.]*physical.slots for _ in directed_links]
        for li,slot,key,record in entries:
            if key is None:
                continue
            eta = cached[key] * 10**(-record['weather_loss_db']/10)
            rate = skr_bps(eta, optical)
            if record['capacity_limit_bps'] is not None:
                rate=min(rate,record['capacity_limit_bps'])
            rows[li][slot]=rate
        info.update(stage='complete', elapsed_seconds=round(time.perf_counter()-start,3))
        if progress:progress(info.copy())
        return rows, info
