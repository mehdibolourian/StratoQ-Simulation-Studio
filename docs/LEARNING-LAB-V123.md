# Learning Lab v1.2.3 — live metrics, finish state, and time grid

This is a focused update to v1.2.2; apply without deleting `backend/.venv`, the Balloon-QNet extension, or cached weather data.

## Installation

From the **existing** StratoQ root directory:

```sh
unzip -o ~/Downloads/StratoQ-Studio-Learning-Lab-v123-Patch.zip
./start-stratoq.sh
```

Stop the old FastAPI/Vite server before running the new launcher. Do not replace or delete `backend/data/learning/`: previous checkpoints and measurements remain stored there. A running v1.2.2 training job uses old Python code; stop it before applying this patch.

## Changes

- **Live chart:** the worker writes `live.json` after each actual completed LP/physical time slot, including checkpoint 0 (initial evaluation), and writes `metrics.json` after each PPO update. The UI polls sequentially every ~750 ms during active runs. A drawn point is a real measured result, not synthetic animation. Optical preprocessing can still take time before any plot point is available.
- **Completion:** when the last episode/checkpoint finishes, the worker atomically records `status=complete`, `episode=episodes`, and `stage=complete`; the UI shows the completed state, a full bar, and no Stop button. No manual stop is required. Polling ends at a terminal state.
- **Baseline evaluation:** optional, disabled by default. When selected, independent SCAR-Q/MCR-Q evaluations run after PPO episodes and before final completion, so startup no longer stalls before the first training episode. The reference cards remain blank unless enabled.
- **Curriculum off:** disabled curriculum parameters are omitted from the client request and ignored in backend curriculum validation; all demands remain active. HTTP 422 errors now display Pydantic field-path details instead of an unhelpful numeric code. Because the original failed request payload wasn't captured, the exact earlier cause of 422 cannot be conclusively established.
- **Time grid:** slot seconds (1–3600, integer) and episode horizon minutes (1–1440, integer) determine `slots=horizon*60/slot_seconds`. The result must be an integer of 1–288 slots and at most 24h; both are copied into the scenario and used by the existing optical and Gurobi environment. For instance 300-second slots and 120-minute horizon = 24 steps; 60-second slots and 60 minutes = 60 steps; a 24-hour horizon with 300-second slots = 288 steps.
- **Topology scaling:** input/output layers still scale with 2 × GS × HAP directed optical links and the number of demands. The time grid changes the rollout length, *not* per-slot input/output dimensions of a feedforward policy. It does not reuse checkpoints across different network topologies.
- **Chart proportions:** preserved SVG aspect ratio, maximum readable width, and dynamic x-axis zoom while training is underway.

## First real-Mac test

With curriculum **off** and baseline comparisons **off**, set 300 seconds / 60 minutes / 2 episodes / checkpoint every 1. Observe measured slot-level progress in initial evaluation and PPO training. Confirm completion without pressing Stop; select episode 0/1/2 for replay. If a 422 error remains, the red banner now names the invalid request field. Training throughput is hardware/physics/Gurobi dependent, and full real optical/LP training was not executed in the build environment.
