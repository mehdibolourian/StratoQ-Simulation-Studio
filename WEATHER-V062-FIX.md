# StratoQ Studio v0.6.2 — Weather reliability fix

## Root cause of HTTP 500

Your traceback points to `backend/stratoq_demo/setup.py`, where the previous backend tries to access `weather.effect` even though its local Pydantic `WeatherRegion` class lacks that attribute. Copying only the React files leaves the exception in place.

This revision fixes the schema and adds a defensive default in `setup.py`. It also handles older `type` / `weather_type` JSON fields (including `cloud` → `fog`).

## Files changed

- `backend/stratoq_demo/models.py` — weather effect schema (`fog` / `rain` / `snow`), validation, legacy aliases
- `backend/stratoq_demo/setup.py` — compatibility fallback for weather records without `effect`
- `backend/main.py` — `/api/health` reports version `0.6.2`
- `backend/tests/test_weather_regression.py` — 7 added regression cases
- `frontend/src/App.jsx` — pinned effect buttons, version mismatch message, drag instructions
- `frontend/src/components/Network3D.jsx` — direct 3D region drag, visible grab handle, non-intercepting particles
- `frontend/src/components/GeoMap.jsx` — map weather polygon drag, effect-specific marker
- `frontend/src/styles.css` — prominent compact weather picker and version alert

## Apply the SMALL patch to your existing repo (recommended)

**Back up / commit your local changes first.** In the root of the project (`.../stratoq-studio`), unzip the patch ZIP so its `frontend/` and `backend/` directories overlay the existing directories:

```bash
cd /Users/mehdi/Files/stratoq-studio
unzip -o ~/Downloads/stratoq-studio-v062-patch.zip
```

Do **not** unzip into `frontend/` or `backend/`; run from the project root. No new npm or Python packages are required beyond the v0.6 installation.

## Restart BOTH processes (the key step)

**Terminal A, backend** (stop the old server with Ctrl+C):

```bash
cd /Users/mehdi/Files/stratoq-studio/backend
source .venv/bin/activate
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Verify the running backend responds with `version: 0.6.2`:

```bash
curl http://127.0.0.1:8000/api/health
```

**Terminal B, frontend** (stop the old Vite process with Ctrl+C):

```bash
cd /Users/mehdi/Files/stratoq-studio/frontend
npm run dev
```

Open `http://127.0.0.1:5173` and hard-refresh (Cmd+Shift+R). The header must say **UI 0.6.2**. The API health endpoint must say **version 0.6.2**. If you see a mismatch message in the UI, a different backend build is running on port 8000.

## Verify the weather behavior

1. Select **Weather regions** to add one. The new region is selected automatically.
2. At the top of the **right panel**, just under **Inspector**, choose **Fog / cloud**, **Rain**, or **Snow**. This control is now outside the scroll area.
3. In **3D**, drag the weather region's colored center knob, or any visible portion of its ground circle. The **Move** tool is no longer required for weather.
4. In **Map view**, drag either its weather marker or the filled circular region.
5. Adjust radius and extra loss further down in the right-side parameter editor.
6. Press **Play** or **Run simulation**; affected link capacities and weather flags update from the placeholder simulator.

## Automated checks

```bash
cd backend
python -m pytest -q
```

Note: weather intersections are still 2D ground-projection approximations, and key rates come from the synthetic simulator. Browser visuals have not been run end-to-end in the build environment.
