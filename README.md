# StratoQ Studio — 3D local network sandbox

A runnable starter for a balloon-assisted QKD visualizer using **React + Vite + React Three Fiber/Three.js + MapLibre GL JS + FastAPI**. It starts with two ground stations and one 15-km high-altitude platform around Timmins / Iroquois Falls, Ontario.

**v0.8 physically calculated links:** The optical rates call the original
`balloon_qnet.transmittance_simulation.channel_theory` numerical model
(LOWTRAN7, turbulence, AO, fiber coupling) and its BB84 SKR equation.
**Only routing and storage allocation remain demo heuristics**, and user weather
patches are applied as configured dB attenuation over 2D path intersections.
See **[REAL-PHYSICS-V08.md](REAL-PHYSICS-V08.md)** for platform prerequisites,
exact execution and cache behavior, full/native verification, and limits.

## Prerequisites

- Node.js **20.19+ or 22.12+** (or newer supported Node.js release), npm
- Python **3.10+**
- WebGL-capable browser (recent Chrome, Firefox or Safari)
- Internet access for **`npm install`** and map tiles (the 3D network scene itself does not use map tiles)

## 1. Unzip the project

Extract `stratoq-studio.zip`. From your terminal:

```bash
cd stratoq-studio
```

## 2. Start the Python API (terminal 1)

macOS / Linux:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

On Windows PowerShell, activate the venv with `.venv\Scripts\Activate.ps1` instead of `source ...`.

API links:
- Health: http://127.0.0.1:8000/api/health
- Swagger interactive docs: http://127.0.0.1:8000/docs

## 3. Start the browser UI (terminal 2)

From the root `stratoq-studio` folder in **another** terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://127.0.0.1:5173** in your browser. The Vite dev server proxies `/api` to FastAPI at `127.0.0.1:8000`.

You should see 2 ground stations, one balloon, a cyan optical network, a right-side inspector, and a timeline. Press **Run simulation** to start the real physical calculations (they do not auto-run on page load).

## 4. Try the demo

1. **Orbit**: In `3D scene`, left-drag the background to rotate the camera; scroll to zoom; right-drag to pan. Use the rotate button to auto-orbit.
2. **Move network elements in 3D**: Click the pointer/move icon at the scene's upper right, then drag a GS or balloon **horizontally**. The altitude stays fixed; change it in the inspector.
3. **Move elements geographically**: Switch to `Map view`; drag GS, balloon or weather markers. Switch back to 3D to see their new positions.
4. **Rotate a 3D model**: Select it and use the `Model heading` slider on the right (the camera can be rotated independently).
5. **Add objects**: Use the left sidebar to add a balloon, GS, cloud region or demand. Edit their parameters on the right.
6. **Test weather**: Add a weather region, set radius and path loss in dB, place it across one link, and click **Run simulation**. The link efficiency and BB84 capacity should decrease.
7. **Playback**: Press play under the 3D scene, or scrub time slots to see key-buffer and demand delivery changes.
8. **Export**: Use `Export scenario` or the inspector's results export icon to save JSON.

**Expected behavior:** edits mark the simulation as out of date. The geometry and map update immediately, but link-rate and demand results update **only after Run simulation**. This prevents expensive recomputation every mouse movement.

## Directory structure

```text
stratoq-studio/
├── backend/
│   ├── main.py                     # FastAPI, CORS, routes
│   ├── requirements.txt
│   ├── stratoq_demo/
│   │   ├── models.py               # Pydantic input/output contract
│   │   ├── setup.py                # GS–HAP topology + weather intersections
│   │   ├── resource_allocator.py   # Toy per-slot key store / greedy allocation
│   │   └── stratoq_adapter.py      # Swap seam for real StratoQ functions
│   └── tests/test_demo.py
└── frontend/
    ├── vite.config.js              # proxy /api → localhost:8000
    └── src/
        ├── App.jsx                 # React editor, inspector, timeline
        ├── components/
        │   ├── Network3D.jsx       # Three.js mesh models, orbital camera, 3D links
        │   └── GeoMap.jsx          # MapLibre draggable markers, geo overlays
        ├── lib/geo.js              # lon/lat/alt → local 3D coordinates
        └── lib/sample.js           # initial case used before API returns
```

## API schema (future-compatible design)

- `GET /api/health`
- `GET /api/scenario/default`
- `POST /api/simulate` with a `Scenario` JSON body, returns a `SimulationResult`

The API returns **frames**, each including `slot`, `time_seconds`, `links`, `demands`, `stored_bits_total`, `served_bps_total`.

Sample request:

```bash
curl -s http://127.0.0.1:8000/api/scenario/default > case.json
curl -s -X POST http://127.0.0.1:8000/api/simulate \
  -H 'Content-Type: application/json' -d @case.json > result.json
```

## Actual upstream theoretical channel — v0.8

Run `python verify_physics.py` in `backend/` before the first large simulation.
This calls the actual LOWTRAN7 Fortran native library and the original
`channel_theory` for both directions. If a dependency is missing it fails
explicitly: **there is no simplified physical model fallback**.

Use `GET /api/physics/status` to check availability of the native module.
The UI starts a monitored job with `POST /api/simulations`, polls
`GET /api/simulations/{id}`, and fetches results only once complete. The
progress bar shows unique link/time physical calculations and cache hits.

Every changed GS/HAP geometry, altitude, wavelength, turbulence, AO or
pointing parameter triggers new channel evaluations upon Run; unaffected
fingerprinted geometry is reused from a SQLite cache. Changes to source
rate/QBER or user weather dB can be applied to the cached channel efficiency.

The resource allocator remains a seeded demonstration heuristic, not your
full StratoQ routing/optimization algorithm. See **REAL-PHYSICS-V08.md**.

**Technical modeling TODO:** Weather currently attenuates a link if the horizontal GS–HAP segment intersects a disk. That is not a vertical 3D atmospheric-volume intersection model. Replace it with altitude-aware path integration if you want physically credible atmospheric effects. The local XYZ projection in the 3D viewer uses an equirectangular tangent-plane approximation for regional-scale scenes; use ENU/ECEF coordinates for larger areas or accurate Earth curvature. Balloon envelope, antenna and station meshes are visually exaggerated and not true-to-scale equipment.

The real physical calculation now uses monitored background jobs with polling.
The legacy synchronous `/api/simulate` route remains for compatibility and debugging.

## Testing / troubleshooting

```bash
cd backend
python -m pytest -q
```

Common issues:

- **Backend offline**: FastAPI must be running on port 8000 before running a simulation. Visit `/api/health`.
- **Blank 3D scene**: Check browser WebGL settings / hardware acceleration and the dev-server console. The 3D renderer requires WebGL.
- **Map tiles missing**: The geographic view requires internet access to load CARTO's public basemap. The local 3D scene remains usable without tiles.
- **npm engine error**: Upgrade Node to the Vite-supported version above.
- **Invalid scenario 422**: Demand endpoints must name different, existing GS IDs; `altitude_km` must be between 0 and 50 (strictly > 0).

For production or shared/public access: add authentication, persistent storage, job isolation, solver runtime limits, and hardened allowed origins. The current API is meant for a local, trusted machine only.

## v0.7 physical-rate update

The network uses a fast **analytical approximation** to compute BB84 link capacities instead of the previous arbitrary/synthetic rate formula. See **[ANALYTICAL-V07.md](ANALYTICAL-V07.md)** for scope, parameter mapping, limitations, tests and exact StratoQ integration seam. UI/API version is `0.7.0`; all source files must be updated together.

## v0.8 physics integration (current)

See [REAL-PHYSICS-V08.md](REAL-PHYSICS-V08.md). UI/API version `0.8.0`; the real
`balloon_qnet` analytical channel is always used, and the browser displays the
actual physical computation progress. The v0.7 approximation is historical and
is no longer on the simulation execution path.
