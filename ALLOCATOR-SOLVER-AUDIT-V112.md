# StratoQ v1.1.2: solver evidence and activation visibility

## What was verified in the previous v1.1.1 source
- Backend `stratoq_demo.stratoq_adapter.simulate()` delegates to `resource_allocator.allocate()`.
- Each slot delegates to `allocator_algorithms.select_and_solve_slot()`, then `solve_slot()`. The latter builds a genuine `gurobipy.Model`, declares rate/storage variables and linear constraints, sets two objectives, and calls `model.optimize()`.
- `Model.Params.OutputFlag = 0` hid the solver log. Rapid completion is possible for small LPs, particularly after cached physical-rate evaluations.
- Source link flags `activated` and `allocated` are propagated from the solver result, and `potentialLinks()` merges frames into the rendered topology. A static visualization with no selected path can be physically consistent.
- **Crucial:** notebook-based SCAR-Q requires the *whole demanded rate* on both hops from either fresh generation on both, or stored QKP on both. If either capacity is below the configured demand, SCAR-Q may choose no path, even when both capacities are positive. MCR-Q allows partial-rate candidate paths. If every rate is zero, neither algorithm can activate links.

## v1.1.2 changes
- Backend now provides `frame.optimizer`: actual completed Gurobi optimize calls, solver status, solver runtime, model size, selected route count, activated links, positive-rate links, and an explanatory note.
- Backend `result.summary` now reports actual optimized models, cumulative Gurobi solver time, version, slot counts, and nonactivated slots. FastAPI prints short per-slot solver reports.
- Inspector displays Gurobi metrics, especially why all optical links may be idle; 3D view displays animated travelling gold photon markers on actual activated links. Map view continues to color activated links gold.
- Enable full Gurobi logging by starting the server with `STRATOQ_GUROBI_LOG=1 python -m uvicorn main:app --port 8000`; this can be verbose for large simulations.
- `backend/verify_allocator_runtime.py` checks real Gurobi optimize results on a controlled 2 GS / 1 HAP example (without performing channel physics); it fails loudly without gurobipy/license.
- Algorithm policies, original physical rates, QKP LP constraints, and source models remain unchanged.

## Installation
Stop Vite and FastAPI. From `/Users/mehdi/Files/stratoq-studio`:

```sh
unzip -o ~/Downloads/stratoq-studio-v112-solver-audit-patch.zip
cd backend
source .venv/bin/activate
python verify_allocator_runtime.py
python -m pytest -q tests/test_allocator_v110.py
python -m uvicorn main:app --port 8000
```

From a separate terminal:

```sh
cd /Users/mehdi/Files/stratoq-studio/frontend
npm run dev -- --force
```

Hard-refresh Chrome (`Cmd+Shift+R`), verify `UI 1.1.2` at top-right. Run a simulation and inspect **Inspector > Network Performance > Gurobi Allocation**. If selected routes and activated links are zero, compare per-link computed `capacity_bps` with demand `rate_bps`, or try MCR-Q (which can route partial requests). If optimization metrics show nonzero activations but the 3D view remains muted, check browser console for a rendering error and verify the frontend is serving `UI 1.1.2`.

## Validation limitations
Source and unit tests pass, but a real Gurobi solve and interactive browser render were not possible in the packaging container (gurobipy unavailable, frontend modules not installed). The bundled runtime check must be run in your working macOS environment. This patch does not prove all of your actual scenario's slots have feasible optical links.
