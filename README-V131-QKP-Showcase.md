# StratoQ v131 — One QKP storage ablation showcase

## Installation
This is an **incremental patch for the v130 project** (the version with 3D link colors and label toggle). Back up your local changes first. Unzip this archive into the **StratoQ-Simulation-Studio-Cleaned project root**, overwriting the relative paths below. No backend solver, channel formula, or simulation engine files are changed. Restart both backend and Vite frontend; refresh the browser.

Your old browser workspace is stored in `localStorage` and **will not be overwritten**. To use the new experiment (instead of old saved "Storm bridge" / "Storm control" tabs), open **Workspace → Replace tabs with showcase set**. Export the workspace first if you want to keep your existing edited scenarios. Alternatively, choose **04 · QKP storm survival** from the built-in selector to open the updated scenario without deleting old tabs.

## Study procedure
1. Open **04 · QKP storm survival | Optimal · 24h** (QKP enabled) and run the solver.
2. Expand **Workspace → QKP ablation · measured comparison** (opened by default for the QKP study), click **Open matched QKP-off control**. This creates or reuses a control copied from the active scenario where only `config.qkp_enabled` changes.
3. Run the control separately. Switch between its tab and QKP-on tab. The comparison panel shows whole-day **delivered/requested end-to-end keys**, **severe-weather delivered/requested keys**, and **difference in percentage points**, plus actual QKP link-key draw.
4. Inspect QKP fill before T+07:00, consumption during T+07:00–17:00 and link recovery after T+17:00. Check **both offline solver gaps/statuses** before claiming proven optimality.

## Why the previous two presets showed only ~64% vs ~60%
The v128 storm scenario had only five hours of fog in the 24-hour denominator, and a single HAP Rx/Tx pair forced its two requests to compete. A small full-horizon QKP effect is therefore possible even if the storm-window impact is visible. Note that results saved in old tabs may also come from different v128/v126 preset versions; the studio now prevents comparing unmatched scenarios. The precise cause of earlier numeric outcomes cannot be established without those original run summaries.

## What the new controlled scenario changes
- Keeps the original 24-hour shifted **measured balloon trajectory**, three Ontario GSs, two requests, theoretical channel calculation, and Optimal MILP.
- Gives the single HAP **2 Tx and 2 Rx optical terminals** so both demand paths can activate; sets GS capacity to **300 Mb** and HAP capacity to **600 Mb**, resulting in up to **200 Mb per GS–HAP link**, before resource allocation.
- Programs fog **T+07:00–17:00** at visibility **0.06 km** over the shared Iroquois Falls optical leg, with rain **T+10:30–13:30** near Cochrane. Both are constructed weather inputs, not observed historical events.
- On the sampled path geometry, modeled Iroquois Falls fog attenuation is about **33–45 dB** during the core disruption, versus 0 dB clear. The 10-hour demand requests around **79 Mb** total from the shared link, below its 200 Mb ceiling; whether it actually accumulates enough requires the native physical rates and solver output.
- Pre-storm generation has seven hours to build inventory. This creates a *plausible* large service difference if the clean-sky physical capacity is sufficient, but the software never forces a desired percentage or inserts fabricated measurements.
- The preconfigured library now has **four** experiments (SCAR-Q, MCR-Q, Optimal corridor, and this one QKP study). The no-QKP control is only created when requested. Reopening a matching built-in tab reuses it instead of silently duplicating it.

## Files changed
- `backend/stratoq_demo/builtin_experiments.json` and synchronized `frontend/src/lib/builtinExperiments.json`: one longer, controlled QKP demo; remove separate default control.
- `frontend/src/App.jsx`: create/reuse exactly matching QKP-off counterpart, compare only inputs identical except storage, show measured deltas, avoid duplicate built-ins.
- `frontend/src/lib/qkpComparison.js`: strict matching and percentage-point helper.
- `frontend/src/lib/showcaseStory.js`: corrected key moments/timings for the longer weather event.
- `frontend/src/styles.css`: readable comparison actions and delta.
- `backend/tests/test_builtin_showcase_v125.py`, `frontend/tests/showcase-story.test.mjs`, `frontend/tests/qkp-comparison.test.mjs`: regression coverage.

## Verification and limitations
- Backend showcase/link-flow tests: **11 passed**.
- Frontend link-visuals, story, and QKP-comparison tests: **10 passed**.
- Changed JSX/JS parsed cleanly using the TypeScript parser.
- A complete `vite build` could **not** run because this environment's `node_modules` is incomplete (`vite: not found`).
- An end-to-end **native LOWTRAN + Gurobi comparison was not run**: `gurobipy` is unavailable and the native LOWTRAN build requires unavailable Meson packages. Consequently, **no specific 60%/40%, 80%/50%, or other numeric outcome is claimed**. Verify resulting measured values in your own environment. If stored-key draw is zero, inspect solver gap, clear-period physical SKR and QKP fill before treating the experiment as a successful demonstration.
