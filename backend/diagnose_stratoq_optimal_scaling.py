#!/usr/bin/env python3
"""Diagnose why StratoQ's offline results change with the time-slot length.

Run from StratoQ's backend directory, using the backend virtual environment:
  python diagnose_stratoq_optimal_scaling.py ../stratoq-experiment.json
  python diagnose_stratoq_optimal_scaling.py ../stratoq-experiment.json --solve
  python diagnose_stratoq_optimal_scaling.py ../stratoq-experiment.json --clear-weather --solve

The exported experiment JSON is read-only and never modified. Prints actual
physical link capacities, a feasible fresh-key-only lower bound for the
1-demand/1-HAP case, and optionally the actual full-horizon Gurobi outcome.
"""
from __future__ import annotations
import argparse
import copy
import json
import math
import statistics
import sys
from pathlib import Path


def as_mbits(value):
    return f'{value / 1e6:,.5f} Mbit'


def stats(values):
    x = [float(v) for v in values if math.isfinite(float(v))]
    if not x:
        return 'no finite values'
    zero = sum(abs(v) < 1e-7 for v in x)
    return (f'min={min(x):.6g}, mean={statistics.mean(x):.6g}, '
            f'median={statistics.median(x):.6g}, max={max(x):.6g} bps; '
            f'zero={zero}/{len(x)}')


def load_scenario(path):
    from stratoq_demo.models import Scenario
    obj = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(obj, dict) and 'scenario' in obj:
        obj = obj['scenario']
    if not isinstance(obj, dict) or 'ground_stations' not in obj:
        raise ValueError('Expected a StratoQ Export Experiment JSON file')
    return Scenario.model_validate(obj)


def available_paths(scenario, physical, dt):
    from stratoq_demo.setup import build_links
    from stratoq_demo.trajectories import scenario_at
    output = []
    for t in range(physical.slots):
        current, _ = scenario_at(scenario, t * dt)
        candidates = build_links(current)
        available = {r['id']: bool(r['enabled'] and r['in_range']) for r in candidates}
        for record in candidates:
            sample = physical.scene_links[record['source'], record['target']][t]
            available[record['id']] = available[record['id']] and bool(sample['in_range'])
        output.append((candidates, available))
    return output


def check_one(scenario, dt, run_solver):
    from stratoq_demo.physical_setup import create_physical_network
    from stratoq_demo.demand_profiles import demand_rates
    from stratoq_demo.offline_allocator import solve_offline
    import inspect
    from stratoq_demo import offline_allocator as oa
    actual_source = inspect.getsource(oa.solve_offline)
    if run_solver and ('discard_only_generated' not in actual_source or
                       'offline_discarded_bits_total' not in actual_source):
        raise RuntimeError(
            'OUTDATED OFFLINE ALLOCATOR imported from: '
            + inspect.getfile(oa) + '\n'
            'The v1.1.6 QKP overflow fix is not loaded. Install and restart '
            'FastAPI before comparing slot durations.'
        )

    scenario = copy.deepcopy(scenario)
    scenario.config.slot_seconds = dt
    scenario.config.slots = math.ceil(86400 / dt)
    scenario.config.allocation_mode = 'optimal'
    physical = create_physical_network(scenario)
    T = physical.slots
    hours = T * dt / 3600.0
    profiles = demand_rates(scenario, T, dt)
    requested = sum(sum(x) for x in profiles.values()) * dt
    links = physical.rate_by_link
    print(f'\n=== dt={dt}s ({dt/60:g} min), slots={T}, horizon={hours:.4f}h ===')
    print('Total requested:', as_mbits(requested))
    for lid, rates in links.items():
        print(f'  K_MAX[{lid}]: {stats(rates)}')
    print('Weather:', scenario.config.weather_source,
          'ERA5 date:', scenario.config.era5_date,
          'manual regions:', len(scenario.weather_regions))

    shots = available_paths(scenario, physical, dt)
    if len(scenario.demands) == 1 and len(scenario.balloons) == 1:
        d = scenario.demands[0]
        h = scenario.balloons[0]
        src = next(x for x in scenario.ground_stations if x.id == d.source)
        dst = next(x for x in scenario.ground_stations if x.id == d.target)
        left = f'{d.source}:{h.id}'
        right = f'{d.target}:{h.id}'
        connects = bool(src.n_tx and dst.n_rx and h.n_tx and h.n_rx)
        baseline = 0.0
        usable = 0
        for t, (_,available) in enumerate(shots):
            if connects and available.get(left) and available.get(right):
                rate = min(profiles[d.id][t], links[left][t], links[right][t])
                baseline += max(0., rate)*dt
                usable += int(rate>1e-7)
        print('Fresh-key-only FEASIBLE lower bound:', as_mbits(baseline),
              f'({100*baseline/requested:.2f}% requested; {usable}/{T} usable slots)')
        print('This lower bound uses neither previous-slot QKP nor storage. '
              'An optimal MILP must serve at least this many bits.')
    else:
        baseline = None
        print('Fresh-key-only bound skipped (requires exactly 1 demand and 1 HAP).')

    if not run_solver:
        return
    import gurobipy as gp
    candidates = shots[0][0]
    gs_capacity = {g.id:g.capacity_bits for g in scenario.ground_stations}
    h_capacity = {h.id:h.capacity_bits for h in scenario.balloons}
    gs_degree = {g.id:sum(l['source']==g.id for l in candidates) for g in scenario.ground_stations}
    h_degree = {h.id:sum(l['target']==h.id for l in candidates) for h in scenario.balloons}
    qkp_max = {l['id']:min(gs_capacity[l['source']]/max(1,gs_degree[l['source']]),
                           h_capacity[l['target']]/max(1,h_degree[l['target']])) for l in candidates}
    print('QKP per-link caps:', {key:as_mbits(v) for key,v in qkp_max.items()})
    # Build every slot's exact link records with the same physical metadata as allocate().
    shots_full = []
    for t,(records, _) in enumerate(shots):
        updated = []
        for record in records:
            record = dict(record)
            physical_sample = physical.scene_links[record['source'],record['target']][t]
            record.update({key:physical_sample[key] for key in ('distance_km','elevation_deg',
                         'in_range','weather_loss_db','weather_flags')})
            updated.append(record)
        shots_full.append(updated)
    rate_history = [{lid:float(values[t]) for lid,values in links.items()} for t in range(T)]
    solutions, info = solve_offline(scenario, shots_full, rate_history, qkp_max, profiles, dt, gp)
    served = sum(sum(slot['served'].values()) for slot in solutions) * dt
    print('Gurobi solver:', info['gurobi_status'], 'MIP gap:', info['achieved_mip_gap'],
          'solver seconds:', round(info['gurobi_runtime_seconds'],4))
    print('Served:',as_mbits(served), f'({100*served/requested:.2f}% of requested)')
    print('Final QKP:', {lid:as_mbits(solutions[-1]['buffers'][lid]) for lid in links})
    if 'offline_discarded_bits_total' in info:
        print('Discarded keys:', as_mbits(info['offline_discarded_bits_total']))
    else:
        print('WARNING: offline_discarded_bits_total is missing from solver output; '
              'outdated offline_allocator likely loaded.')
    if baseline is not None:
        if served + max(1.,1e-7 * max(baseline,1.)) < baseline:
            print('*** PROBLEM: Gurobi incumbent is WORSE than a feasible fresh-only baseline. ***')
            print('Investigate solver status/gap and offline_allocator formulation/installation.')
        else:
            print('PASS: Offline result meets the feasible fresh-key-only lower bound.')


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('experiment',type=Path,help='Export Experiment JSON from StratoQ')
    p.add_argument('--durations',type=int,nargs='+',default=[600,900,1800,3600],
                   help='Slot durations in seconds (default: 600 900 1800 3600)')
    p.add_argument('--solve',action='store_true',help='Also run real Gurobi offline MILPs (slow)')
    p.add_argument('--clear-weather',action='store_true',help='Remove ERA5/manual weather for an isolation test')
    args=p.parse_args()
    if any(v <= 0 for v in args.durations):p.error('Slot durations must be positive')
    scenario=load_scenario(args.experiment)
    if args.clear_weather:
        scenario.config.weather_source='manual'
        scenario.config.era5_dataset_id=None
        scenario.config.era5_date=None
        scenario.weather_regions=[]
    print('Experiment:',args.experiment.resolve())
    print('Nodes:',len(scenario.ground_stations),'GS /',len(scenario.balloons),'HAP;',
          len(scenario.demands),'demands')
    for dt in args.durations:
        check_one(scenario,dt,args.solve)
    return 0


if __name__=='__main__':
    sys.exit(main())
