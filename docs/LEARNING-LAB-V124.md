# StratoQ Studio — Learning Lab v1.2.4

This is a **focused UI, telemetry, and 3D camera patch** based on v1.2.3.
The physics engine, Gurobi formulation, PPO architecture, training objective,
and main simulation algorithm implementations are unchanged.

## What changed

1. **No arbitrary 1,000-episode limit.** Positive integral episode counts and
   checkpoint intervals are accepted by both the form and FastAPI. JavaScript's
   safe-integer range still applies to the browser's numeric input. This is a
   numeric-precision safeguard, **not** a training-episode cap. Extremely long
   jobs still take real compute time, storage, and checkpoints.
2. **Streaming, scalable training histories.** New jobs persist every completed
   episode to `backend/data/learning/<run-id>/metrics.jsonl`, with fixed-width
   `metrics.offsets` seek-index. `/api/learning/runs/<id>/metrics?since=N`
   returns only episodes later than N; `max_points=1800` requests an extrema-
   preserving visual preview. Existing pre-v1.2.4 `metrics.json` runs still load.
   Short new runs also retain `metrics.json` for compatibility, while long runs
   use only the append-only stream from episode 101 onward to avoid quadratic
   disk I/O. All actual measurements remain in JSONL; preview compaction does
   not alter the stored experiment or agent training.
3. **Adaptive plot rendering.** Small dots for a few episodes, progressively
   thinner marks as measurements accumulate, and line-only history at high
   density (with the latest dot visible). The SVG keeps its aspect ratio and
   stops expanding across arbitrarily wide dashboard layouts.
4. **Scrollable, paged checkpoint list.** At most 200 checkpoint buttons are
   mounted at once; First/Previous/Next/Latest navigate the full history.
   The section is independently scrollable, not an infinitely growing panel.
5. **Matched time-grid labels.** Slot length / seconds and episode horizon /
   minutes now use two consistently aligned label lines.
6. **PPO architecture and diagnostics panel.** Shows the actual observation
   features `7 * (2 * GS * HAP) + 6 * demands`, encoder width, two residual
   blocks, actor logits `HAP * (demands + 1)`, scalar critic, derived trainable
   parameter count, completed episodes, rollout slots, and measured PPO
   policy loss, value loss, entropy and entropy coefficient. No synthetic
   performance numbers are inserted.
7. **Bounds-aware Network Studio 3D scene.** The ground plane, grid, axes and
   camera fit follow the current GS/HAP positions and manually edited weather
   zones, even far from the original Ontario origin. Automatic refit occurs
   after a node drag finishes, not while its pointer is captured. The original
   world-to-geographic drag conversion and physical coordinate system remain
   unchanged. ERA5 display cells are not used to inflate the editor camera
   extent. Existing Reset camera button still works.

## Use

Stop training and both running servers, then overlay the incremental patch
inside `StratoQ-Simulation-Studio-Cleaned`:

```bash
cd /Users/mehdi/Files/StratoQ-Simulation-Studio-Cleaned
unzip -o ~/Downloads/StratoQ-Studio-Learning-Lab-v124-Patch.zip
./start-stratoq.sh
```

No virtual-environment recreation, pip reinstall, LOWTRAN rebuild, or Conda
activation is necessary to apply this patch.

For a long run use a **sensible checkpoint interval**, such as 50 or 100
rather than evaluating and saving an entire checkpoint after every episode.
The interface no longer caps the interval either.

## Verification in this environment

- 20 targeted backend tests pass, including acceptance of 100,000 episodes,
  JSONL incremental retrieval and a 3,500-episode preview.
- The existing PPO unit tests still pass with a mocked optical/Gurobi solver
  for integration; no false throughput claims are made.
- Node test confirms layout bounds, 3D axes and plane adapt when HAP coordinates
  move far outside the initial Ontario scene.
- LearningLab.jsx and Network3D.jsx pass JSX parser checks.
- A full Vite build could not run: the npm cache was missing the `zustand`
  archive and the package registry was inaccessible. Actual browser/WebGL and
  licensed Gurobi/Balloon-QNet runs need local validation on macOS.
