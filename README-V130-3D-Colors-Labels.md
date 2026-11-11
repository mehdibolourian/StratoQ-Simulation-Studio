# StratoQ v130 — 3D demand-color fix and label visibility toggle

## Installation

**Incremental patch for the v129 UI visibility patch.** You have already
installed v129 if your node/QKP labels are enlarged and 2D map links change
brightness with throughput. Back up the frontend, then unzip this archive in
`StratoQ-Simulation-Studio-Cleaned/`, keeping folder paths and replacing the
six frontend files. Restart Vite (`cd frontend && npm run dev`) and hard-refresh
the page. No backend restart or recomputation is necessary.

To start from v128 Full, apply the v129 patch first, then this v130 patch.
Do not apply v130 to a project with additional local modifications to any of
these six files without checking the diff first.

## What changed and why

1. **Exact demand colors in 2D and 3D:** Three.js's `Color.setStyle`
   does not consistently parse the modern space-separated CSS HSL strings
   that MapLibre accepts. `demandColor()` now emits the universally
   recognized `hsl(h, s%, l%)` form, preserving the SAME hue and rate-dependent
   lightness in both renderers. It does not change rate normalization.
2. **Reduced 3D link flicker:** The wide, almost-invisible white hit-test line
   previously wrote to the depth buffer directly on top of the colored link.
   It is now fully transparent with depth testing/writing disabled, preserving
   clickability without covering the visible line. Colored lanes, QKP stripes,
   and selection outlines also avoid depth writes and have deterministic draw
   ordering to reduce overlapping-line interference when orbiting the scene.
3. **Unified fallback colors:** Optical ON, QKP-only, mixed, inactive, and
   unavailable physical links without served demand lanes now use one shared
   palette in the 2D map and 3D scene (`linkFallbackColor`).
4. **Labels on/off:** The new `Labels on` button in the 3D scene's upper-right
   toolbar toggles node names and QKP percentages, QKP tank captions,
   physical-link capacities and status labels, weather text, axis annotations,
   and the node-label leader lines. Geometry, animated photons, key packets,
   line rates, mouse interactions, playback, and the bottom demand-color
   legend remain visible. Toggle defaults to ON and is retained when switching
   back and forth between Map and 3D during the same app session.
5. **No physics/allocator changes.** 2D basemap text is unaffected by the 3D
   label toggle; MapLibre's geographical names remain available.

## Files changed

- `frontend/src/App.jsx`
- `frontend/src/components/Network3D.jsx`
- `frontend/src/components/GeoMap.jsx`
- `frontend/src/lib/linkVisuals.js`
- `frontend/src/styles.css`
- `frontend/tests/linkVisuals.v128.test.mjs`

## Checks

- PASS `node frontend/tests/linkVisuals.v128.test.mjs`
- PASS `node frontend/scripts/verify-link-states.mjs`
- PASS TypeScript/JSX parser on edited components and JS modules
- Full Vite production build and interactive browser/WebGL rotation not
  executed in this environment (frontend dependencies are not installed).
  Please confirm visually with a scene containing two demands and differing
  link rates, then rotate the 3D camera and toggle Labels on/off.
