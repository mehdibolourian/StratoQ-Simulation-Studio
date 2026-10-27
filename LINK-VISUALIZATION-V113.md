# StratoQ Studio v1.1.3: physical optical-link animation fix

The visualized optical links must be **GS–HAP**, not the straight GS–GS
line representing a demand. In slot 7, the actual backend result has
`selected_paths=1`, `activated_links=0`: no new optical generation, so
there cannot be moving gold optical photons in that slot. When
`allocated=true` and `activated=false`, the link carries keys from stored
QKP and must be animated **amber**, along the actual GS–HAP segment.

## Code corrections

- `potentialLinks()` now uses the backend `frame.links` geometry and link
  status rather than re-gating `activated` and `allocated` with a separate
  approximate frontend coverage calculation.
- `resolveVisualLinks()` overlays backend frame states on every physical
  link rendered in Three.js and MapLibre, keeping both views synchronized
  with the Inspector.
- Animated gold photon pairs appear only for active optical generation.
  Amber moving photons appear for QKP-only link utilization. Idle links are
  subdued blue. Straight GS–GS demand-arc lines were removed from the 3D
  scene; they previously obscured the actual HAP optical path.
- The 3D legend and the right-hand Inspector now show per-slot counts of
  optical and stored-key-only GS–HAP links.
- For trajectory-equipped HAPs, the inspector distinguishes the editable
  initial coordinates from the frame's current interpolated position.

## Simulation and solver notes

No backend solver or physical code was modified. The user's independent
`backend/verify_allocator_runtime.py` already demonstrates Gurobi 13.0.3
solves OPTIMAL models and activates both physical optical links on a small
example. The reported solver runtime of ~0.0001s is possible for a tiny
LP; it excludes LOWTRAN, link-rate computation, scene updates, and other
wall-clock costs. `activated` is the routing stage's optical generation
switch, not a measurement that fresh `r_1` was nonzero. The counts are
valid for the implemented optimization model but do not validate all
physical assumptions or reproducibility of the full reference algorithms.

## Install and verify

From the Studio project root:

```bash
unzip -o ~/Downloads/stratoq-studio-v113-link-visualization-patch.zip
bash verify-stratoq-v113.sh
cd frontend
npm run dev -- --force
```

Hard-refresh Chrome (Cmd+Shift+R), look for **UI 1.1.3**, run the
simulation and scrub slots 1–24. At a slot with >0 optical activation,
observe moving gold photons on GS–HAP links. At slot 7 with 0 active
optical links and 2 QKP-only links, expect moving amber photons on both
GS–HAP links. If the solver produces 0 activated *and* 0 allocated
links, neither highlight should appear.

## Validation

`node frontend/scripts/verify-link-states.mjs` tests the JS state resolver
without installing npm packages. Source-level checks cover animation
component use and absence of GS–GS demand overlays. Full browser/WebGL
rendering still needs user verification on the Mac.
