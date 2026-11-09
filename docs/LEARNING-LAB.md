# StratoQ Studio — Learning Lab v1.2.1

## Run

From the **latest** patched Studio project root:

```bash
./start-stratoq.sh
```

The launcher creates/reuses the isolated `backend/.venv` (Python 3.10),
installs new requirements (including PyTorch), applies existing SciPy/LOWTRAN
macOS native compatibility checks, and starts both frontend and API. The
first PyTorch installation may require a substantial download. Keep a valid
Gurobi license configured. Go to **Learning Lab** in the Network Studio header.

The first job precomputes actual upstream Balloon-QNet channel key-generation
rates (and reuses the existing physical-rate cache on subsequent jobs). The
initial evaluation and SCAR-Q/MCR-Q reference calculations occur before the
first PPO episode, so the curve may remain empty while the channel evaluates.

**No channel approximation or invented PPO measurements are substituted.**

## Scope of this initial demonstration

- **Fixed controlled topology:** 3 GSs (Timmins, Iroquois Falls, Cochrane), 2
  stationary HAPs, 3 competing GS-pair demands. This is **not** the paper's
  measured-flight Topology 2: it is explicitly an initial, interpretable
  training sandbox in the same geographical region.
- **Real physics and optimization:** `create_physical_network()` computes
  directional upstream key rates, the current Studio LP uses conservative
  shared GS–HAP pair rates, and `solve_slot()` applies the original Gurobi
  per-slot fresh/stored key allocation and bounded shared per-link QKPs.
- **PPO adaptation:** Observation size is `7*(2*GS*HAP) + 6*demands`, with
  directed link features and per-demand features (matching the general
  feature grouping in the paper). Actor output size is
  `HAP*(demands+1)` (one idle/demand choice per HAP); hidden width scales
  from input dimensions. On each new topology size a new neural network is
  initialized and checkpoints are labeled by their architecture.
- **Constrained decisions:** Feasible two-hop paths are computed from actual
  rates; the action sampler enforces idle availability, unique demand
  assignment and available GS Tx/Rx ports. One HAP serves at most one
  demand in the current preset. Joint PPO log-probabilities use the exact
  same sequential masking during sampling and model updates.
- **Learning curriculum:** Initial third of training activates one demand,
  second third activates up to two, last third activates all. The sampled
  demand subset is fixed throughout each training episode; the *frozen*
  evaluation always uses all demands. This is an interactive shortened version
  of the paper's progressive curriculum, not the literal 500/1000 schedule.
- **Training:** PPO with clipped objective, GAE, value loss, entropy bonus,
  Adam `1e-4`, five epochs, batch size 64, discount 0.99 and GAE lambda
  0.95. Shaped training reward is calculated against SCAR-Q and MCR-Q
  solutions from **the same agent QKP state** using stable demand IDs.
  Training demand multipliers are independently sampled from [0.70, 1.30]
  each episode plus a known small sinusoidal time profile; the optical
  channel rates themselves are **never fabricated or randomized**.
- **Checkpoint evaluations:** The policy is frozen (no weight updates),
  greedily selects feasible actions for a fixed demand schedule, and runs
  independent key-pool histories. Episode 0 is evaluated before training.
  The chart displays actual served/requested percentages. The displayed
  evaluation reward is per-demand demand satisfaction; the training shaped
  reward is a *different quantity*, so they are labeled independently.
- **Comparison baselines:** SCAR-Q and MCR-Q run independently on the same
  fixed evaluation inputs, not by reusing PPO's history. MCR-Q currently
  uses 1 random candidate for a fast interactive demonstration.
- **Replay:** Per-slot links, transmitted keys, QKP levels, selected paths,
  and HAP positions reuse the existing Studio `SimulationFrame` format and
  `Network3D` scene. The 3D visualization does not compute outcomes.

This is a sound way to show learning *behavior*; it is not yet evidence of
cross-topology generalization, superiority over the paper baselines, or
paper-level convergence on a held-out trajectory. Short training runs may
not show monotonic improvements; the UI never constructs a fake trend.

## Saved data / inspecting failures

Each experiment creates `backend/data/learning/<run-id>/` with:

- `config.json`, `topology.json`: setup and exact policy shape
- `metrics.json`: one measurement record per completed training episode
- `status.json`: current progress and any error
- `baselines.json`: fixed evaluation SCAR-Q/MCR-Q results in bits
- `checkpoint_000000.pt` and later: actual PyTorch `state_dict` weights
- `evaluation_000000.json` and later: frozen checkpoint metrics and real frames
- `run.log`, `pid`: subprocess debugging and lifecycle

Endpoints: `GET /api/learning/preset`, `GET /api/learning/latest`,
`POST /api/learning/runs`, `GET /api/learning/runs/{id}`,
`GET /api/learning/runs/{id}/metrics`,
`GET /api/learning/runs/{id}/evaluation/{episode}`,
`POST /api/learning/runs/{id}/stop`.

For a short first check, choose **12 slots, 2 episodes, checkpoint interval 1**.
Only after that successfully finishes should you attempt 30+ episodes.

## Why not import the original notebook trainer wholesale?

The paper-aligned notebook expects a fixed canonical 6 GS / 6 HAP superset,
72 directed links, 15 demands, five external 24-hour wind trajectory CSVs,
and its own `online_new` data classes / state registry. This first Learning
Lab has a smaller fixed Studio topology and an independent Studio physics
pipeline. Importing the notebook trainer without adapting its data model,
channel-rate units, directed-link representation, and QKP state would give
inconsistent results. We instead reuse the paper-inspired feature grouping,
masked actions, reward shaping and PPO update while retaining the Studio
solver and physical model. Full paper reproduction belongs in a separate,
validated experimental integration; do not label these initial metrics as
published paper results.

## Verification

```bash
./start-stratoq.sh --doctor
backend/.venv/bin/python -m pytest -q backend/tests/test_learning_lab.py
```

Seven new unit/integration tests check topology scaling, per-node masks,
reward indexing, actual PyTorch PPO weight changes, per-slot 3D replay frames,
full job/checkpoint persistence, and progressive curriculum with intentionally mocked physics / LP.
They are **not** a replacement for one real Gurobi + Balloon-QNet training
job on the target Mac.
