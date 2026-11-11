# StratoQ v132 — Clean 24-hour demo + PPO learning defaults

**Install on top of v131** (already incorporating the v129/v130 2D/3D color and label fixes). This ZIP is **not a complete project**. Extract it into the `StratoQ-Simulation-Studio-Cleaned` project root and allow the 14 files to overwrite/add. Restart the FastAPI backend and the Vite frontend, then refresh the browser. Back up any changes made locally to those files before applying the patch.

## Four cases: one shared network

| Tab | What changes? | QKP | Duration |
| --- | --- | --- | --- |
| 01 · SCAR-Q | Scarcity-first online allocator | On | 24h |
| 02 · MCR-Q | Sample candidate online allocations | On | 24h |
| 03 · Optimal · QKP on | Full-horizon optimizer | On | 24h |
| 04 · Optimal · QKP off | Same full-horizon optimizer | Off | 24h |

All four have the **identical** 24-hour measured balloon flight `builtin:csv-ontario-24h`, same three Ontario ground stations, same single HAP, two key-rate demands, optical parameters, storage capacities, weather, seed, terminal counts, and 144×600-second grid. MCR-Q uses the same candidate count setting everywhere; only the allocation mode or QKP availability differs. The former 6-hour SCAR/MCR/Optimal corridor scenarios and old redundant storm-control copies are no longer bundled; there is no separate duplicate Optimal tab.

**Simple demo:** Open SCAR-Q to explain greedy per-slot allocation, MCR-Q to show candidate search, then Optimal/QKP on and Optimal/QKP off to isolate the importance of key storage. Within any tab follow: 00:00–07:00 clear sky (potential key accumulation); 07:00–10:30 fog; 10:30–17:00 fog with temporary overlapping rain (rain stops at 13:30); 17:00–24:00 recovery. Compare full-day and 07:00–17:00 served/requested end-to-end key percentages in the sidebar; only real solver output appears, no percentages are scripted. Note that the full-horizon Optimal runs can time out with nonzero gap, so inspect solver status before calling the incumbent optimal.

### Old saved tabs

On initial reload, the Studio automatically replaces **untouched legacy built-in tabs** and repeated duplicates with the four current demos. User-edited experiments and custom tabs are preserved. For a completely clean workspace, choose **Workspace → Reset to four demos**; this discards all tabs after explicit confirmation. Export your workspace first if needed. Previous simulation results are not carried over.

## Learning Lab default changes (PPO reward model unchanged)

| Parameter | v131 | v132 | Why |
| --- | ---: | ---: | --- |
| Episodes | 30 | **48** | More independent full-complexity episodes |
| Checkpoint every | 5 | **6** | Regular fixed-workload evaluation, not every rollout |
| Curriculum stage 1 cutoff | 33% | **12%** | Short introduction to one demand |
| Curriculum stage 2 cutoff | 67% | **30%** | Reach all three demands earlier |
| Stage 3 workload | ~10 of 30 | **34 of 48 episodes** | ~71% of training now uses all demands |
| Learning rate | 0.0001 | **0.0002** | More decisive policy updates within the available episodes |
| PPO update epochs | 5 | **8** | More optimization passes over each collected rollout |
| Mini-batch size | 64 | **16** | Two minibatches per typical 24-slot episode instead of one |
| Entropy coefficient (start → end) | 0.01 → 0.001 | **0.008 → 0.0003** | Lower late-stage exploration after curriculum reaches full difficulty |

Unchanged: **reward function**, gamma 0.99, GAE lambda 0.95, PPO clip 0.2, rollout/observation/action/solver model, checkpoint evaluation on all demands. Settings remain editable. The changes apply to **new training jobs only** and do not retroactively change saved checkpoints. A longer 48-episode run requires more LP solves and policy updates than 30 episodes; for a short live smoke test choose 2–4 episodes, but such a smoke test cannot demonstrate genuine multi-stage learning.

## Validation

- Backend: 28 focused tests passed (preset alignment, physical snapshot handoff, Learning Lab, curriculum/defaults).
- Frontend: 13 tests passed (story, QKP ablation, link visuals, old-workspace migration).
- All changed JS/JSX parsed using the TypeScript parser; Python files compiled successfully.
- The full Vite build and an actual native LOWTRAN+Gurobi 24h solver run / PPO training were **not executed** here; unavailable native dependencies prevent asserting a measured QKP percentage gap or improved RL learning curve. The adjustments are reasonable training defaults, **not empirical proof** of convergence.

Files are copied relative to the project root; no backend resource allocator, demand rates, physical-channel model, or PPO reward function was edited.
