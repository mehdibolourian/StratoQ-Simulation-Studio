"""Regression: offline optical generation must not force QKP overflow at long slots.

These integration tests need gurobipy and a valid Gurobi license. Run:
    cd backend && python -m pytest -q tests/test_offline_qkp_overflow_v116.py
"""
import pytest
from stratoq_demo.setup import default_scenario, build_links
from stratoq_demo.offline_allocator import solve_offline


def _solve(dt, total_seconds=3600, storage_bits=200_000, source_bps=5_000,
           demand_bps=4_000):
    gp = pytest.importorskip('gurobipy')
    assert total_seconds % dt == 0
    s = default_scenario()
    s.config.allocation_mode = 'optimal'
    s.config.optimality_gap = 0.
    s.config.optimal_time_limit_seconds = 60
    n = total_seconds // dt
    s.demands[0].rate_bps = demand_bps
    links = build_links(s)
    ids = [r['id'] for r in links]
    rate_history = [{lid: source_bps for lid in ids} for _ in range(n)]
    slots = [links for _ in range(n)]
    solved, stats = solve_offline(
        s, slots, rate_history, {lid: storage_bits for lid in ids},
        {'d-1': [demand_bps]*n}, dt, gp)
    return solved, stats, ids


@pytest.mark.parametrize('seconds', [600, 900, 1800, 3600])
def test_identical_one_hour_demand_independent_of_slot_duration(seconds):
    slots, info, ids = _solve(seconds)
    assert info['gurobi_status'] == 'OPTIMAL'
    total = sum(s['served']['d-1'] for s in slots) * seconds
    assert total == pytest.approx(4000 * 3600, rel=1e-7)
    assert all(s['served']['d-1'] == pytest.approx(4000., rel=1e-7) for s in slots)
    assert info['offline_discarded_bits_total'] > 0
    for slot in slots:
        for lid in ids:
            assert 0 <= slot['buffers'][lid] <= 200_000 + 1e-5
            assert slot['discarded_bits'][lid] >= 0
    assert sum(s['optimizer']['discarded_bits_total'] for s in slots) == pytest.approx(
        info['offline_discarded_bits_total'])


def test_qkp_carryover_still_works_at_30_minutes():
    gp = pytest.importorskip('gurobipy')
    s = default_scenario()
    s.config.allocation_mode = 'optimal'
    s.config.optimality_gap = 0.
    s.config.optimal_time_limit_seconds = 60
    links = build_links(s)
    ids = [r['id'] for r in links]
    rates = [{lid: 5000. for lid in ids}, {lid: 0. for lid in ids}]
    solved, info = solve_offline(
        s, [links, links], rates, {lid: 2_000_000. for lid in ids},
        {'d-1': [4000., 4000.]}, 1800, gp)
    assert info['gurobi_status'] == 'OPTIMAL'
    # The objective maximizes the two-slot total; first/second split is
    # degenerate, so do not require a particular storage/use schedule.
    assert solved[0]['served']['d-1'] > 0.
    assert solved[1]['served']['d-1'] > 0.
    assert sum(x['served']['d-1'] for x in solved) == pytest.approx(5000., rel=1e-7)
    assert not solved[1]['activated']
    assert sum(s['served']['d-1'] for s in solved)*1800 == pytest.approx(9_000_000.)
