# StratoQ Simulation Studio — SCAR-Q / MCR-Q correction (v1.1.1)

**Reference:** User-supplied `hap-qkd-online-path-based-dynamic-NEW.ipynb`, code cell containing `scarq_policy` and `mcr_policy`; `online.py` contains the original `online_new` Gurobi allocation concepts. This is a Studio adaptation of the *online* policies for one-HAP GS→HAP→GS routes, not a verbatim import of the notebook's global objects or offline evaluation.

## Correct algorithm definitions

### SCAR-Q — greedy scarcity/contention aware (not Monte Carlo)

For each time slot:

1. Enumerate GS→HAP→GS paths for each demand.
2. A greedy candidate requires **both** hops to individually support the complete demand via **fresh** per-slot key capacity (`K_MAX >= K_REQ` on each hop) **or both** hops to individually support it via **previously stored** keys (`A_prev/THETA >= K_REQ` on each hop). This matches `scarq_policy` in the notebook; partial fresh+stored mixed paths may still be served by the LP once a route is selected, but do not qualify during greedy candidate generation unless one of those two full-feasibility cases holds.
3. Rank demands by **fewest feasible paths**, then **larger key requirement**.
4. Rank paths by summed link contention (how many feasible demand paths use each link). Greedily reserve available HAP Tx/Rx and configured GS ports.
5. Solve the Gurobi key-rate LP **once**, and commit its QKP next-state.

### MCR-Q — Monte Carlo routing (not maximum-capacity routing)

For each time slot:

1. Create **N** independent randomized candidate assignments (default **N=3**, matching notebook `mcr_policy(..., n_samples=3)`). Each candidate shuffles demand order and randomly chooses a feasible one-HAP path that respects port limits.
2. For **each candidate**, construct and optimize the **actual Gurobi LP** (fresh key flows, stored-key flows, end-to-end served rates, QKP carryover/storage limit).
3. Compare candidates by **total served keys** (`sum_d r_h[d] * THETA`), retaining the first winner on ties.
4. Commit **only the winning candidate's** QKP next-state. Losing samples do not mutate the next time slot.

A seeded `random.Random(seed + slot)` makes choices reproducible for a given topology and time horizon. Change the MCR-Q **Monte Carlo samples** and **Random seed** fields under **Inspector → Simulation Config**. For N samples and S slots, MCR-Q solves N×S LPs; SCAR-Q solves S LPs.

## Gurobi and model adaptation

The backend retains the v1.1.0 **real Gurobi** per-slot model with `r_h`, `r_1`, `r_2`, and `A_next`, subject to fresh key-rate capacity, QKP inventory, storage conservation/capacity and fixed selected paths. Slot paths and `activated`/`allocated` flags are returned for the existing animated gold link highlights. Upstream channel physics/LOWTRAN and historical weather are untouched.

**Important model distinction:** Routing decisions are *heuristic/randomized*, not jointly optimized by Gurobi. Gurobi optimizes rates and inventories **for each selected candidate**. This adapts the notebook to Studio's symmetric per-link GS–HAP key-inventory representation and existing endpoint port limits; it is not an identical reproduction of all original model constraints. The notebook's explicit `link_active` input is approximated here by available capacity/QKP on Studio's potential link set. Further validation is appropriate for research-grade comparisons, especially terminal availability during outages.

## Backward compatibility

Legacy export settings now map **`random` → `mcr_q`** and **`greedy` → `scar_q`**. Files exported from v1.1.0 that *already* contain `scar_q` or `mcr_q` cannot be automatically remapped, so review the selected algorithm after importing an old workspace.

The API contract remains `1.0.5`; the UI build marker is now `1.1.1`. Default `mcr_samples=3` is automatically supplied to older experiments. The existing animation, Open-Meteo, workspace, branding, native files and historical data paths are not altered.

## Installation

Stop FastAPI and Vite, then from the Studio project root:

```bash
cd /Users/mehdi/Files/stratoq-studio
unzip -o ~/Downloads/stratoq-studio-v111-mcr-monte-carlo-patch.zip
bash verify-stratoq-v111.sh
```

Restart the backend **in the Gurobi-enabled Python environment**:

```bash
cd backend
source .venv/bin/activate
python -c 'import gurobipy as gp; print("Gurobi", gp.gurobi.version())'
python -m pytest -q tests/test_allocator_v110.py
python -m uvicorn main:app --port 8000
```

In a second terminal:

```bash
cd /Users/mehdi/Files/stratoq-studio/frontend
npm run dev -- --force
```

Hard-refresh Chrome (`Cmd+Shift+R`). The top-right chip should display `UI 1.1.1`. Open **Simulation Config** and select the algorithm. When MCR-Q is selected, Monte Carlo sample count and seed controls appear.

## Tests and limitations

Packaging environment: **17 tests passed, 1 skipped** (allocator + weather/queue focused suites). The skipped test runs real Gurobi because `gurobipy` is not available here and cannot be fetched in this environment. Older tests that launch complete simulations also cannot pass without Gurobi; they exit at the intended dependency check, not at a routing failure. No live Gurobi/Mac browser run was available for verification. The sampled path policies and best-candidate comparison were tested with a controlled solver stub; the production solver is still actual Gurobi, with no stub fallback.
