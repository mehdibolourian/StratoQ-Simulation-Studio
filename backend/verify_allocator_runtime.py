"""Run a real, tiny Gurobi-backed SCAR-Q and MCR-Q allocation independently of LOWTRAN.

From backend/ with venv activated:
    python verify_allocator_runtime.py

This is a controlled optimizer smoke test, not proof that a full physical
simulation produced positive K_MAX for the chosen day/topology.
"""
from stratoq_demo.allocator_algorithms import require_gurobi, select_and_solve_slot
from stratoq_demo.setup import default_scenario


def main():
    gp = require_gurobi()
    scenario = default_scenario()
    seconds = scenario.config.slot_seconds
    rates = {f'{g.id}:{h.id}': 5_000.0 for g in scenario.ground_stations for h in scenario.balloons}
    previous = {key: 0.0 for key in rates}
    capacity = {key: 2_000_000.0 for key in rates}
    for method, samples in [('scar_q', 1), ('mcr_q', 3)]:
        audit = {}
        paths, solved = select_and_solve_slot(
            scenario, rates, previous, capacity, seconds,
            method, seed=42, n_samples=samples, gp=gp, trace=audit,
        )
        served, live, stored, active, next_qkp, objective = solved
        print(f"{method}: Gurobi={audit['gurobi_version']} status={audit['solver_status']} "
              f"models={audit['candidate_solves']} vars={audit['gurobi_variable_count']} "
              f"constraints={audit['gurobi_constraint_count']} "
              f"runtime={audit['gurobi_runtime_seconds']:.6f}s "
              f"selected_paths={len(paths)} activated={sorted(active)} "
              f"served_bps={sum(served.values()):.2f} QKP={next_qkp}")
        assert audit['solver_status'] == 'OPTIMAL', audit
        assert audit['candidate_solves'] == samples, audit
        assert audit['gurobi_variable_count'] > 0, audit
        assert len(active) == 2, active
        assert abs(objective - 1_200_000) < .1, objective
    print('PASS: both algorithms solved real Gurobi models and activated two optical links.')

if __name__ == '__main__':
    main()
