# StratoQ Studio v1.2.7 — Guided experiment stories

## Objective

Show what makes the three allocation philosophies different, and make QKP storage a measurable story rather than an assumption.

No physics, allocator, input scenario, weather model, Gurobi formulation or scientific rate calculation was modified. Guided cues consume the existing `SimulationResult.frames` and `summary` produced by the original backend.

## Finding and using the guide

1. Open one of the built-in showcase experiments from **Workspace → Built-in showcase experiments**. Previously opened built-in tabs work too.
2. The **Experiment story** button appears next to the 3D/Map view switch and a persistent **Experiment story** rail appears below the time scrubber. The center panel can scroll vertically on short screens.
3. The rail shows concise, time-linked labels and translucent ranges for the planned narrative phases. They are visible *before* running the simulation.
4. Click any label to jump to the relevant slot. After a run, the label shifts to a measured interesting slot *within that same phase*, if a relevant observation is found. Otherwise it remains at the scheduled inspection point and explicitly reports that the expected observation was not found.
5. Click **View full story** to open a modal with the premise, algorithmic mechanism, chapter-by-chapter walkthrough, and how to analyze the measured results. Each chapter can jump to its slot. A comparison table shows results of matching experiments that have been run within the current browser session.

## Five stories

| Built-in experiment | Narration | What to inspect |
|---|---|---|
| 01 · SCAR-Q | Scarce routes get priority | Initially activated optical links, chosen demand routes, demand peaks, changes during rain/fog, recovery |
| 02 · MCR-Q | Search for better joint choices | Number of candidate optimizations, chosen paths, whether search changes served-key results |
| 03 · Offline Optimal | Plan across the whole horizon | Early activation and storage, later storage consumption or rerouting, certified gap versus incumbent |
| 04 · Optimal + QKP | Can stored keys bridge a storm? | Buffer build-up before 10h, actual QKP consumption or depletion during 10–15h fog/rain, recovery |
| 05 · Optimal without QKP | What happens without the reserve? | Fresh-key service before, during, and after the identical storm; compare with QKP-on control |

The 6-hour corridor scenarios all use the same 4-GS/3-HAP trajectories and six demands. The 24-hour storm pair uses the same trajectory, weather, requests and time grid, with QKP availability as the designed difference.

## Scientific integrity

- **Scheduled inspection** means a designed input condition or viewing question, *not* a claimed solver result. When a run does not contain the sought event (e.g. no buffer depletion), the UI says so.
- **Measured cue** means a specific signal is present in a result frame: activated optical link(s), a route change, candidate searches, a served-key change, positive QKP draw, positive/negative inventory delta, or blocked demands.
- A marker can move only **within its scheduled story window**. It does not add or change simulation events.
- Per-slot displayed metrics use actual `frame.demands`, `frame.links`, `frame.stored_bits_total`, `frame.qkp_drawn_link_bits`, and `frame.optimizer`.
- QKP draw counts **link-key bits** and is not interchangeable with end-to-end served bits.
- A storage advantage must be shown by **measured storm-window delivered keys** versus the matched QKP-off experiment; QKP usage alone does not prove a throughput benefit.
- An offline Gurobi result without an accepted gap is an incumbent, not necessarily certified optimal.
- Historical tabs can have shorter horizons. Their labels are trimmed to the saved horizon and the existing 24h preset-opening action remains available.

## Source files

- `frontend/src/lib/showcaseStory.js`: curated narrative beats, per-slot measurement extraction, signal detection and time slot mapping.
- `frontend/src/components/ShowcaseStory.jsx`: always-visible time-linked rail and full-story modal.
- `frontend/src/App.jsx`: wire guides to built-in preset tabs, playback, current results and matching comparisons.
- `frontend/src/styles.css`: story UI and accessible center-panel scrolling.
- `frontend/tests/showcase-story.test.mjs`: 7 node tests for narratives, historic tabs, real-vs-scheduled cues and buffers.

## Test

```bash
cd frontend
node --test tests/showcase-story.test.mjs
```

The full Vite production build and browser interaction require installed npm dependencies; they were not available in the artifact build environment. Native Gurobi/LOWTRAN simulation was not run here; verify a real experiment on the Mac installation.
