# StratoQ v1.2.6 — Showcase playback corrections

## Scope
This patch modifies only camera framing, Files dropdown behavior, the bundled CSV trajectory duration for paired storm presets, and concise event-based showcase guidance. It does **not** change the optical physics, SCAR-Q/MCR-Q selection, the offline MILP, PPO, resource scheduling, or rates. The previous five-hour tabs in local browser storage remain intact; use **Open updated 24h preset** from the timeline, or open a fresh built-in experiment, to get the updated 24-hour cases.

## Two experimental durations (deliberate)
The matched four-GS/three-HAP SCAR-Q, MCR-Q, and offline Optimal comparisons remain **6 h / 15 min = 24 slots**. The May 5 and June 1 Excel traces only provide high-altitude intervals for those synthetic geographical translations, so the three-algorithm comparison cannot honestly be described as 24 h.

The paired 3-GS/one-HAP **Optimal + QKP** and **Optimal with QKP disabled** scenarios now use the **entire 24-hour CSV trace**, sampled at 60-second intervals and simulated on **144 ten-minute slots**. Both use identical translated coordinates and weather; only storage is toggled. Pre-storm clear weather extends until hour 10; fog is scheduled from 10:00–15:00 (30-minute ramps), and overlapping rain from 11:00–13:00 (20-minute ramps). This gives pre-storm accumulation, disruption, and recovery phases. `builtin:csv-ontario-6h` remains available for older experiments and the comparison corridor; new key `builtin:csv-ontario-24h` persists across restarts.

**Important:** The original measured CSV flight's motion is reproduced, but the geographical translation and weather are constructed research scenarios, not measured weather or additional independent flights. Longer 24-hour full-horizon optimization may take substantially longer and may hit the existing 240-second MILP limit. Check solver incumbent/certification and actual key rates before claiming a QKP improvement.

## Playback and UI
- The 3D scene computes updated bounds, but **does not reset camera azimuth/elevation during playback**. After manual network editing it can refit distance/target while keeping your chosen orientation; Reset Camera still returns to the initial view. A distant HAP may move the camera target by translation, never by forced rotation.
- Files is a properly styled dropdown independent of an obsolete UI-version CSS selector. It closes on outside click, Escape, or file action.
- The timeline displays clickable **Key moments** with exact 1-based slot numbers and elapsed simulation times. The marker points to the first sampled slot where an event is active, not an unsampled fraction of a slot. A concise explanation and *measured current-slot demand and QKP draw* appears only when the playhead reaches a marker. **Read more** expands only that marker's rationale. No computed allocation outcome is predeclared.
- Older sidebar prose has been removed/reduced. Solver diagnostics and measured benchmark comparison remain accessible, with comparison collapsed by default.

## Local validation
Run `cd backend && PYTHONPATH=. pytest -q tests/test_builtin_showcase_v125.py` for the eight showcase regression checks. The test file name retains its original version to avoid deleting test history. Tests include 24-hour duration, weather-to-link handoff, matching QKP pair, and scheduled milestone bounds. The final test on the target Mac is a real 24-hour native LOWTRAN/Gurobi run and browser rotation/dropdown check.
