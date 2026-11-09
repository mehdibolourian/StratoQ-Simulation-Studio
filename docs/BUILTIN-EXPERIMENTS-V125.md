**Superseded by [v1.2.6 changes](BUILTIN-EXPERIMENTS-V126.md).** This document describes the previous five-hour built-in storm settings; current built-in storm presets use 24 hours.

# StratoQ v1.2.5 — Built-in scenario showcase and translated flight trajectories

## Quick start

Install the patch into your existing Studio directory and run `./start-stratoq.sh`. In **Network Studio → Workspace → Built-in showcase experiments**, choose an experiment, or select **Replace tabs with showcase set**. The latter asks before replacing saved tabs; exporting your current workspace first is recommended. New browser workspaces start with the five built-in experiments. Existing locally saved workspaces are preserved until explicitly replaced.

The cases have editable GSs, HAPs, optical configuration, demand rates/patterns, weather schedules, trajectories, and algorithm. They are reproducible without reuploading the three original data files; embedded, deterministic trace IDs survive backend restarts. The original uploaded files are **not** overwritten. The built-ins are snapshots of those files sampled at 60-second intervals with linear interpolation. Test settings use slots of 600 or 900 seconds.

## Study 1: Scarcity-first vs sampled alternatives vs offline foresight

Three matched **6-hour** scenarios with four geographic GSs (Timmins, Iroquois Falls, Cochrane, Kirkland Lake), three mobile stratospheric HAPs, and **six simultaneous directed GS-pair demands**. Every unordered GS pair is represented once; the orientation is chosen in the scenario. Loads are deliberately illustrative *application key-consumption rates*, not measured customer traffic. They mix constant, dual-peak, single-peak and bursty patterns between 1.4–2.3 kb/s mean. Six-hour horizon at 15-minute slots (24 frames). Terminal limit: one TX/RX per node.

- **01 SCAR-Q — scarcity-first**: prioritize demand with fewer feasible paths and choose lower-contended HAP. Inspect which route it protects and what is blocked when a link is contested.
- **02 MCR-Q — candidate search**: 16 seeded randomized candidates per slot, each with the same per-slot Gurobi LP. Inspect selected route changes and multiple candidate solves.
- **03 Optimal — whole-horizon**: full-horizon Gurobi MILP, 2% target MIP gap / 240 s limit. Inspector reports whether the result is *certified optimal* or only a time-limited incumbent. It sees future demand and weather, unlike online algorithms; comparisons are descriptive, not an online information-equivalent performance claim.

These scenarios use the May 5 and June 1 North Bay flights and the 24-hour CSV flight, separately shifted into one synthetic regional scenario. Both Excel flights are excerpted from their actual high-altitude segments (4–10 hours for May, 3–9 hours for June), removing near-ground ascent/descent that could make a regional HAP QKD demo physically misleading. They are **not concurrent measured flights**. The rain band (7 mm/h) develops and drifts across a 6-hour horizon; valley fog (0.55 km visibility) appears later. Optical weather loss is computed by Studio's existing path/layer attenuation equations at every slot. The weather is a constructed deterministic scenario, **not historical observations or ERA5**.

## Study 2: QKP mitigates a scheduled storm

- **04 Optimal + QKP**: 3 GSs, 1 mobile HAP (translated CSV track), 2 concurrent key demands, 5-hour horizon at 10-minute slots, 1% target MIP gap, max 240 s. Fog onset around T+105 min, strong by T+120 min, dissipates around T+255 min; overlapping rain affects the Cochrane region for a shorter interval. The offline MILP can accumulate link-local QKP keys from excess optical generation when a route is activated, then consume saved keys when generation declines.
- **05 Optimal / no QKP**: same inputs and solver settings, but *effective QKP link capacity is set to zero* via `config.qkp_enabled=false` (physical optics and demand profiles unchanged). Watch stored-key-only links and compare delivered bits, especially during the storm. Stored bits in this control are exactly zero.

This is a paired **controlled experiment**, not an assertion that QKP necessarily wins on every channel instance. Because the offline MILP maximizes delivered keys, the result depends on actual channel SKRs, QKP limits and numerical optimization gap. If it does not show a clear QKP benefit, verify optical rates and initial buffer growth; do not fabricate curves or increase reported performance. The existing MILP activates a link only when a demand uses it; it **does not proactively accumulate keys on idle routes**. This is a limitation of the existing model, intentionally unchanged here.

## Translating a trajectory

Select a HAP → **HAP trajectory → Trajectory start**. Choose **Original recorded first point** or **Shift first point to selected location**, then set target latitude and longitude (or drag the HAP). The backend applies the delta between the first source point and target to **all subsequent geographic coordinates**. Altitude, elapsed times, and relative motion are unchanged. This is a spatial translation of the observed dynamics, not an independent wind simulation; it must not be interpreted as a real flight at the shifted location. This works with both uploaded and embedded built-in traces and persists in experiment JSON.

## Time-dependent manual weather

Select a weather region → **Time-varying weather profile**. Set start/end hours, fade-in/out minutes and eastward drift (degrees/hour). The backend snapshots weather at each simulation time step, applies physical fog/rain/snow attenuation to intersecting optical paths, and forwards the active weather regions to 3D/map playback. The GUI and loss calculations use the same timed snapshot. By contrast, ERA5 remains optional and independent.

## Changes, restrictions and validation

Only built-in experiment management, trajectory time sampling/translation, weather inputs, QKP on/off for controlled comparisons, and explanatory UI were changed. No underlying Balloon-QNet formulas, SCAR-Q/MCR-Q selection heuristics, PPO code, or offline Gurobi mathematical constraints were rewritten. Optical fallback rates are not introduced. Expensive end-to-end native LOWTRAN/Gurobi optimization must be verified on the target Mac. On first run, theoretical channel evaluations for many moving HAP positions can take time; the disk cache is reused on subsequent comparisons.
