# StratoQ v133 — Configurable Reward Shaping & PPO Diagnostics

**Incremental patch for the v132 project.** Only the files listed below are replaced. No scene, physics, optimizer, solver, or paper-training data files are modified.

## Install

1. Back up the v132 project.
2. Extract `StratoQ-v133-Reward-Tuning-Patch.zip` **into the `StratoQ-Simulation-Studio-Cleaned` project root**, keeping the `backend/` and `frontend/` paths and allowing overwrites.
3. Restart both the backend and the frontend, and hard-refresh your browser.
4. Open **Learning Lab → Training configuration → Reward function · advanced**. The section starts collapsed to avoid clutter.
5. Changes take effect **only for newly started training jobs**; existing jobs/checkpoints are not rewritten.

## Files changed

- `backend/stratoq_demo/learning_core.py` — validated, tunable reward constants; opt-in zero-service guard; accurate threshold ratios; PPO diagnostics (approximate KL, clip fraction, relative parameter movement).
- `backend/stratoq_demo/learning_worker.py` — forwards selected reward configuration into actual per-slot reward calculation, saves settings with run/checkpoints, reports PPO diagnostics.
- `backend/main.py` — API request fields, defaults and validation.
- `frontend/src/components/LearningLab.jsx` — reward controls and reset, worked example, diagnostics, reward-only plot with trailing average instead of mixing incomparable metrics.
- `backend/tests/test_v133_reward_controls.py` — new parameter, worker, edge-case, API, and PPO tests.

## Default reward (unchanged mathematical definition)

For demand satisfaction `rho`, and best/worst heuristic satisfaction `hi`/`lo`, the default piecewise expression is:

- `rho >= 0.95`: `1`
- `hi <= rho < 0.95`: `0.6 + 0.4*(rho-hi)`
- `lo <= rho < hi`: `0.1 + 0.1*(rho-lo)/(hi-lo+1e-8)`
- `rho < lo`: `-1*(lo-rho)`

All **seven** numerical constants are editable individually:

| API / config property | Paper default | Meaning |
|---|---:|---|
| `reward_success_threshold` | 0.95 | Satisfaction threshold triggering full reward |
| `reward_success` | 1.0 | Reward at/above the threshold |
| `reward_at_or_above_hi` | 0.6 | Base reward for matching the better heuristic |
| `reward_above_hi_slope` | 0.4 | Extra reward per satisfaction unit above the better heuristic |
| `reward_between_base` | 0.1 | Base reward between heuristics |
| `reward_between_gain` | 0.1 | Gain on normalized interval between the heuristics |
| `reward_below_slope` | 1.0 | Penalty multiplier for worse-than-both outcomes |

`reward_zero_service_guard` is a separate **experimental boolean** (default `false`). With the original formula, an agent that serves **zero** when both heuristics serve **zero** receives **+0.6**, even though nothing was delivered. With the guard enabled, this one all-zero case returns `0` instead. **The guard departs from the paper equation; it is opt-in** so default runs remain paper-aligned. `epsilon = 1e-8` in the between-heuristics denominator remains fixed as a numerical stabilizer.

A small numeric correctness fix removes an unnecessary `+1e-8` from the strictly positive requested-key denominator when constructing the satisfaction ratios. This prevents an **exactly** 95%-served demand from falling just below the 0.95 threshold due to roundoff. The formula itself is otherwise unchanged at the defaults.

### Exploratory values (not a claimed better-trained policy)

For your first A/B test against the old reward, hold topology, physical rates, seed, PPO settings and curriculum fixed; change only:

- `reward_at_or_above_hi = 0.25` (instead of 0.6)
- `reward_between_base = 0.05` (instead of 0.1)
- `reward_between_gain = 0.20` (instead of 0.1)
- `reward_above_hi_slope = 1.2` (instead of 0.4)
- `reward_zero_service_guard = true`

Leave the threshold/reward-at-success and below-heuristic penalty unchanged for this first comparison. These choices shrink the large bonus for merely matching a heuristic and give a stronger incentive for improvement above it. They **do not** eliminate the jump at 95% or guarantee convergence; inspect actual fixed-checkpoint keys served. Changes in reward scale affect PPO advantages and the critic, so single-run conclusions should be treated as exploratory. If these values are used, they are **not the published paper reward**.

## Better learning interpretation

The old **Reward** chart overlaid heuristic-relative training reward with *satisfaction-based* evaluation reward. These are different quantities; visual comparison was misleading. The new Reward view shows only heuristic-relative training reward plus an observed 25-episode trailing average. The **Keys served** view remains the appropriate place to compare frozen deterministic evaluations at checkpoints on identical fixed workloads. It also shows training satisfaction, but training data vary across episodes/curriculum, so only the frozen-evaluation series is strictly comparable over time.

The model diagnostics now also include:

- **Approx. PPO KL:** update divergence for batches in that episode;
- **Clipped updates:** fraction of samples falling outside the PPO clipping interval;
- **Policy weight change:** relative L2 parameter change per episode;
- existing **entropy** and **value/policy losses**.

A nonzero weight change does not guarantee different decisions; a flat evaluation curve could also reflect deterministic action saturation, physical bottlenecks, or inadequate exploration. Use the diagnostics and fixed-checkpoint rate to investigate rather than infer a cause from one graph.

## Validation

- 34 focused backend tests passed (includes the new reward controls and existing learning pipeline).
- 13 existing frontend tests passed.
- Edited Python compiled and edited JSX parsed successfully with TypeScript's JSX parser.
- A full frontend Vite build was not available here (frontend dependencies not installed).
- The full backend test suite had 108 passes, 8 skips, and 23 failures caused by missing native Gurobi; full physical optimization and PPO training with Gurobi/LOWTRAN were **not** executed.

No performance gain is claimed. New runs must actually be measured on your machine.
