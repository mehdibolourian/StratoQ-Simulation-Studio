# StratoQ Simulation Studio v1.1.4 — Demand, Horizon, Offline MILP, UI

This is a **patch against v1.1.3**. Extract it at the project root (the directory containing `backend/` and `frontend/`). It does not replace `balloon_qnet`, native LOWTRAN, ERA5 data, or any compiled binaries.

## 1. Total served and requested keys

The Gurobi section in the Inspector shows **full-run served bits**, **full-run requested bits**, and **overall served fraction**, distinct from the selected time slot's `bps` rate. The backend integrates each requested/served demand rate over its slot duration (in seconds). Summary fields: `total_served_bits`, `total_requested_bits`, `total_satisfaction`, `horizon_seconds`.

## 2. Demand patterns

Select any **demand** in the left menu or scene. Choose Constant, Diurnal Gaussian, Two daily peaks, or Periodic bursts. Adjustable fields include mean rate (bps), peak-hour position, peak uplift above mean (%), Gaussian width, second peak position/strength, or burst interval/duration. The Inspector displays a live SVG preview. All generated nonnegative rates are normalized to the specified *mean across the simulated horizon*; peak uplift describes the relative maximum **before positivity clipping and mean re-normalization**, so extreme settings may shift the exact realized peak. Profiles repeat each simulated day. `backend/stratoq_demo/demand_profiles.py` and `frontend/src/lib/demandProfiles.js` implement identical formulas.

Existing saved experiments lacking `pattern` use Constant. The backend supplies the per-slot profile to **both** the online allocator and the original StratoQ-compatible `K_REQ` sequences.

## 3. Simulation horizon

Default: 24 hours. `10s → 8,640 slots; 30s → 2,880; 60s → 1,440; 300s → 288`. When a trajectory is uploaded, the shortest attached trajectory duration determines the horizon; imported timestamps are normalized relative to the first valid sample so a nonzero initial `Time_s` does not inflate the horizon; an included `trajectory_duration_seconds` field retains that information in exported experiment JSON. The frontend calculates the slot count automatically. The backend accepts explicit `slots` for backwards compatibility with API/research clients; newly created API configs that omit `slots` default to the full-day count. ERA5 remains limited to one UTC day. The last partially filled trajectory slot is approximated at full `slot_seconds` resolution, so for nonmultiples of the slot size it may extend by **less than one slot** past the uploaded endpoint; fractional-slot key integration is not implemented.

**Compute warning:** 10-second slots across 24 hours are 8,640 frames and can be costly for LOWTRAN and Gurobi. The UI must not silently cut the horizon back to 1,500 slots.

## 4. Optimal (offline, full-horizon)

The new `optimal` option is an **actual horizon-wide Gurobi MILP**, inspired by `offline.py`, **case 2: maximize total served keys**. It uses binary GS–HAP–GS path assignments and per-link optical activation; continuous per-path served rates, fresh-key rates, stored-key consumption, and per-slot QKP inventories; link-rate and node Tx/Rx limits; and key carryover through time. Unlike the online heuristics, it jointly chooses decisions for the whole horizon. The general MTZ ordering variables in the provided research model are unnecessary for Studio's currently supported **one-HAP** paths. This is not an implementation of the full general multihop formulation nor its case-1 served-demand-count objective.

`optimality_gap` passes directly into `model.Params.MIPGap`; `optimal_time_limit_seconds` passes into `model.Params.TimeLimit`. This is a **single primary objective** (served bits), so the displayed final MIP gap pertains to served bits. If time limit is reached and an incumbent exists, its status is shown as `TIME_LIMIT`; if no incumbent exists, the simulation reports an explicit error. An `OPTIMAL` status means Gurobi certified the user-set gap tolerance, **not necessarily exact zero-gap optimality**.

The user already has Gurobi 13.0.3 installed on their Mac. This packaging environment does not have Gurobi and cannot run the new MILP, so the included `backend/verify_offline_runtime.py` should be run in the backend `.venv` to verify a real 2-slot solve and intertemporal QKP use. **No heuristic fallback** is used if Gurobi is unavailable.

## 5. Visual palette

The UI keeps dark navy/slate surfaces but replaces high-intensity gold primary buttons and labels with **muted lavender-plum** (a restrained nod to Waterloo's purple family). Optical-link gold/amber animations remain unchanged because those colors distinguish optical generation from QKP-only routing. The official Waterloo wordmark and Networks Lab link remain unchanged. The three-orbit favicon and top-left atom mark are both recolored to the same muted purple asset, preserving their exact visual match.

## Installation

```bash
cd /Users/mehdi/Files/stratoq-studio
unzip -o ~/Downloads/stratoq-studio-v114-features-patch.zip
bash verify-stratoq-v114.sh
cd backend
source .venv/bin/activate
python verify_offline_runtime.py
python -m uvicorn main:app --port 8000
# In a second terminal:
cd /Users/mehdi/Files/stratoq-studio/frontend
npm run dev -- --force
```

Restart **both** FastAPI and Vite. The server's compatibility version stays `1.0.5`; the frontend build marker is `1.1.4`.

## Verification / limitations

- Targeted Python tests and frontend parsing/source smoke checks are included.
- Offline MILP is intentionally **not marked runtime-verified** in this environment without Gurobi.
- End-to-end LOWTRAN+MILP+WebGL and latency for 8,640 slots remain to be validated on the user's Mac.
- Trajectory IDs and weather cube IDs remain backend session-scoped; exported experiment JSON does not embed those external assets.
