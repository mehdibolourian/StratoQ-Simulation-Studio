# StratoQ Studio v129 — link visualization and label readability patch

Applies to the supplied **v128 Full** project. This archive contains **only the modified frontend files** under `frontend/`, plus this README. It does not change the allocator, model, API, topology, or simulation outputs.

## Install

1. Back up or commit your current frontend changes.
2. Unzip `StratoQ-v129-UI-Visibility-Patch.zip` in the **project root** (`StratoQ-Simulation-Studio-Cleaned/`), preserving paths and overwriting the six listed files. If you put the archive somewhere else, copy its `frontend/` directory contents over the matching existing files.
3. Restart the Vite development server (restarting FastAPI is not required):

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

4. Hard-refresh the browser tab if old styling remains cached.

## Changes

- **Physical-link rate luminance:** Demands keep their distinct hues. Optical-ON links are compared by actual per-slot `capacity_bps` (link SKR); QKP-only links by actual per-slot `qkp_used_bps` (draw rate). Both line brightness and line width change with the relative rate across the same slot. Carried demand rate also contributes to lane brightness so a demand dimming during bad weather remains visible. QKP inventory (`stored_bits`) is not mistakenly treated as a rate.
- **Optical vs. QKP state:** Optical ON means a **continuous** colored line plus moving round photon pulses; QKP ONLY/OPTICAL OFF means **dashed** colored line with contrasting amber squares. When both are active, the colored solid optical path gets an offset, amber dashed QKP stripe with square packets. No white dashed overlay washes out demand colors. The 2D map uses equivalent solid/dashed/amber treatments.
- **Persistent, larger labels in 3D:** Removed Drei `Html.distanceFactor` camera-dependent scaling for node, link, weather, axis, and QKP tank labels. Ground-station/HAP names, QKP percentages, link-rate labels, and link states are set in readable CSS pixels. Status and rate are stacked in one annotation to prevent them from colliding with each other. QKP-only links show the **draw rate** instead of the 0 optical generation capacity.
- **State truthfulness:** Uses `activated` and `qkp_used_bps` separately, so a link drawing QKP while its optical transmitter is also activated is shown as **OPTICAL ON + QKP**, not falsely QKP-only. Existing legacy saved-result behavior is retained.
- **Legend:** Updated for solid optical, dashed QKP, mixed, and link-rate brightness/width.

## Modified files

- `frontend/src/lib/linkVisuals.js`
- `frontend/src/components/Network3D.jsx`
- `frontend/src/components/GeoMap.jsx`
- `frontend/src/styles.css`
- `frontend/src/App.jsx`
- `frontend/tests/linkVisuals.v128.test.mjs`

## Checks performed

- `node tests/linkVisuals.v128.test.mjs` — PASS, including new relative-link-rate and QKP-only/mixed regressions.
- `node scripts/verify-link-states.mjs` — PASS.
- TypeScript parser syntax check on edited JS/JSX — PASS.
- Full `npm run build` **not verified**: the environment could not finish dependency installation (`npm ci` missing cached dependencies / installation failed).
- Existing `tests/showcase-story.test.mjs` reports one failing assertion involving experiment takeaways. The story files and data are identical to the uploaded v128 versions; not a result of this patch.

To validate visually after install, compare two links with unequal SKR, advance to a slot with stored QKP consumption, and rotate/zoom in the 3D scene: text remains the same size while the displayed link colors, widths, and states update from the current solver frame.
