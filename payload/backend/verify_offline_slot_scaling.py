"""Diagnose 10/15/30/60-minute offline slot scaling with a controlled 1-hour horizon.

Run inside the backend environment: python verify_offline_slot_scaling.py
Requires gurobipy and a valid Gurobi license; independent of LOWTRAN/cache.
"""
import gurobipy as gp
from stratoq_demo.setup import default_scenario, build_links
from stratoq_demo.offline_allocator import solve_offline

s = default_scenario()
s.config.allocation_mode = 'optimal'
s.config.optimality_gap = 0.0
s.config.optimal_time_limit_seconds = 60
records = build_links(s)
ids = [r['id'] for r in records]
expected = 4000.0 * 3600.0
print('Gurobi:', gp.gurobi.version(), '\nExpected served keys across same 1h horizon:', expected)
for dt in [600, 900, 1800, 3600]:
    slots = 3600 // dt
    frames, info = solve_offline(
        s, [records for _ in range(slots)],
        [{lid: 5000.0 for lid in ids} for _ in range(slots)],
        {lid: 200_000.0 for lid in ids},
        {'d-1': [4000.0] * slots}, dt, gp)
    actual = sum(fr['served']['d-1'] for fr in frames) * dt
    spill = info['offline_discarded_bits_total']
    print(f'{dt:4d}s | {slots:2d} slots | status={info["gurobi_status"]:10s} '
          f'| served={actual:.1f}/{expected:.1f} | discarded={spill:.1f} bits '
          f'| MIPGap={info["achieved_mip_gap"]:.3%}')
    assert abs(actual - expected) <= 1e-5*expected, f'Unexpected under-service at {dt}s'
    assert spill > 0, 'Expected excess keys to be discarded with a small buffer'
print('PASS: offline solver serves constant demand at all slot durations; QKP overflow is handled')
