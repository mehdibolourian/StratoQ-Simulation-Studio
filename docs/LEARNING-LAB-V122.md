# StratoQ Learning Lab v1.2.2 — editable fixed-network PPO training

This release adds a user-arranged, **fixed-geometry** network editor and a responsive, per-slot learning monitor. This is a Studio-specific experiment based on the current Studio physical model and Gurobi slot LP. It is **not** a reproduction of the paper's five simulated training trajectories and held-out real-flight results.

## Quick start

1. Apply the incremental ZIP from the root of your current `StratoQ-Simulation-Studio-Cleaned` directory (or use the full ZIP in a fresh directory).
2. Run `./start-stratoq.sh` as before. The same launcher runs FastAPI and Vite and manages the existing project environment. The patch does **not** replace `backend/.venv` or your LOWTRAN binary.
3. Open **Learning Lab**. The Northern Ontario 3-GS/2-HAP scenario is an editable starting point. You can also select **Use Studio network** to copy the currently active Network Studio experiment.
4. Arrange GS and HAP locations in 3D (**Move nodes**) or on the map; add/remove GS, HAP, demands, or weather; select entities to change position, storage, terminal counts, demand endpoints and rates; enable/disable individual GS–HAP links.
5. Set **12 slots, 2 episodes, checkpoint every 1** for a quick functional smoke test, then press **Start new PPO training**. Increase only after the scientific run succeeds.

A copied trajectory-bearing HAP becomes a clearly announced **static snapshot** at the current configured coordinates, without modifying the original Studio experiment. This fixed-topology demo does not silently train against a moving trajectory. Other optical settings, link limits, weather fields and ERA5 references are copied unchanged.

## What is live?

- The UI polls run status, completed-episode metrics, and the **current partial episode** every ~900 ms.
- The worker persists after each full physical slot: current episode and slot, cumulative per-slot reward, cumulative bits served and cumulative demand satisfaction. The partial-episode marker moves from one fractional episode to the next; completed episode dots remain in the chart and are connected.
- It also displays physical-rate computation progress, episode-0 evaluation slot progress, SCAR-Q/MCR-Q reference evaluation slot progress, and the exact training-stage/slot position. This makes the CPU/Gurobi phases visible instead of showing an apparently idle plot.
- Episode 0 **evaluates the untrained policy before running the reference baselines**, so a first genuine point appears sooner. The baseline values are attached after their independent evaluation completes.
- **No synthetic reward or key rates** are used in the application. If real physical or optimization computations fail, the job fails explicitly. Unit tests use controlled mock data only.

Changing topology, demand counts or optical conditions creates a new training run. The backend saves the entire fixed scenario and initializes a fresh actor–critic whose input dimension is `7 × 2 × #GS × #HAP + 6 × #demands`, output dimension is `#HAP × (#demands + 1)` and width depends on observation size. Existing trained weights are never silently adapted to a new shape.

## Configurable PPO parameters

| Setting | Default | Description |
|---|---:|---|
| Learning rate | `1e-4` | Adam step size |
| Discount factor γ | `0.99` | Future reward discount |
| GAE λ | `0.95` | Generalized advantage estimation |
| Clipping ε | `0.20` | PPO probability-ratio clipping |
| PPO update epochs | `5` | Passes over each episode's rollout |
| Mini-batch size | `64` | Rollout samples per policy update |
| Entropy coefficient | `0.01 → 0.001` | Linear anneal over all episodes |
| Curriculum learning | On | Progressive active-demand count by episode |
| Curriculum stages | `1 → 2 → all` | User-selectable first and second demand counts (clamped to topology size) |
| Curriculum transitions | `33%`, `67%` | Episode fraction ending first / second stage |

If curriculum is **off**, every episode trains with all demands. If it is **on**, each episode selects a fresh random subset of the configured active-demand count; it remains fixed for that episode. Curriculum-inactive demands are action-masked so they cannot consume available HAP actions or GS ports. **Frozen checkpoint evaluations always use the same full-demand scenario**, making those points comparable across stages.

The chart's training reward uses the heuristic-relative shaping implemented by the Studio adaptation. Its *evaluation reward* uses mean per-demand satisfaction. The chart labels distinguish them, and throughput satisfaction is the primary apples-to-apples comparison. Increasing training reward during curriculum transitions is not, by itself, evidence of improved full-network performance.

## Persisted run data

`backend/data/learning/<run-id>/` includes `config.json` (complete scenario and hyperparameters), `topology.json` (policy dimensions), `status.json`, `live.json` (last partial-episode record), `metrics.json`, `checkpoint_*.pt`, `evaluation_*.json`, independent heuristic `baselines.json` and `run.log`.

## Limits and validation

- First iteration supports **2–8 GSs, 1–6 HAPs, 1–20 demands**, and **12/24/48 five-minute slots** to limit unbounded interactive compute. The policy dimensions scale automatically inside this range. These are UI/demo workload limits, not a claim that PPO can't handle larger networks.
- Real native Balloon-QNet/LOWTRAN and licensed Gurobi have to be present in the local `.venv`. Rebuilding them is not part of the Learning Lab patch.
- This release only changes the Learning Lab backend, API integration, frontend learning screen, styles and learning tests. The core allocation algorithms and optical channel computations are unchanged.
- The automated backend suite covers data validation, scaling, curriculum, reward/action masking, slot progress, checkpoint files and FastAPI validation. A full scientific run must still be validated on the target macOS hardware.
