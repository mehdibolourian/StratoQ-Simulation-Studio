# StratoQ Studio v1.2.8 — install

1. Stop old FastAPI and Vite servers (Ctrl+C).
2. From your existing `StratoQ-Simulation-Studio-Cleaned` project root run:

```bash
unzip -o ~/Downloads/StratoQ-Studio-v128-Compact-Timeline-Demand-Paths-Patch.zip
./start-stratoq.sh
```

3. Hard refresh `http://127.0.0.1:5173`. Existing saved experiments remain in browser storage.
4. The timeline starts compact. Use its chevron to expand story cues and time-slot controls. The separate `Experiment story` button opens the popup.
5. The map `Reset Scenario` control restores the active tab's original configuration; Run Simulation recomputes results. To create the old 2-GS/1-HAP starter, choose New Experiment.
6. Demand colors match between the 3D view, map, legend, list and link inspector. Solid paths use fresh keys, dashed overlays show QKP link-key usage. Shared links show parallel demand lanes. To make a real-day weather copy, open Experiment story and select Try historical ERA5 2024-06-21.

See `docs/WHAT-CHANGED-V128.md` for details and caveats.
