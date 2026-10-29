# StratoQ Simulation Studio

Local React/Vite + FastAPI simulator for balloon-assisted QKD networks, with the original `balloon_qnet` optical-channel/LOWTRAN model and Gurobi resource allocation. The code includes SCAR-Q, MCR-Q, and a full-horizon offline MILP, the experiment workspace, time-varying demand profiles, and historical ERA5 weather through Open-Meteo. **No approximate channel substitute is used if the scientific backend is unavailable.**

## Start (macOS)

**Run from the project root.** You do not need to activate Conda or `.venv`.

```bash
chmod +x start-stratoq.sh start-stratoq-backend.sh start-stratoq-frontend.sh
./start-stratoq.sh
```

The first launch creates `backend/.venv` with **Python 3.10**, installs Python packages from `backend/requirements.txt`, installs frontend packages using `npm ci` when needed, validates the compiled SciPy, Gurobi and LOWTRAN imports, then starts the API (port **8000**) and UI (port **5173**). Subsequent launches reuse healthy installations. FastAPI runs without `--reload` to avoid interrupting simulation/weather jobs. Stop with Ctrl+C.

Prerequisites: a working **Python 3.10** interpreter (the bundled macOS LOWTRAN library targets Python 3.10 / Apple Silicon); Node.js compatible with Vite 7 and npm; network access for the first dependency install and new Open-Meteo downloads; and a valid Gurobi license. The script will *not* silently use the `hap-qkd` notebook environment, Conda's globally installed SciPy, or a different Python ABI.

If `python3.10` is not on your PATH, specify the interpreter **once per launch** without activating its environment:

```bash
STRATOQ_PYTHON=/opt/miniconda3/bin/python3.10 ./start-stratoq.sh
```

Supported commands:

| Command | Purpose |
|---|---|
| `./start-stratoq.sh` | Automatically prepare environment and start API + frontend |
| `./start-stratoq.sh --setup` | Install / repair dependencies, then exit |
| `./start-stratoq.sh --doctor` | Verify the installed backend environment without installing |
| `./start-stratoq.sh --backend` | Start backend only (also `./start-stratoq-backend.sh`) |
| `./start-stratoq.sh --frontend` | Start frontend only (also `./start-stratoq-frontend.sh`) |
| `STRATOQ_DEEP_PREFLIGHT=1 ./start-stratoq.sh --doctor` | Run a real optical-channel calculation before the demo |

**A broken environment is preserved**, e.g. `backend/.venv-broken-...`, rather than deleted. Automatic dependency repair only installs into `backend/.venv`; it does not change Conda base or `hap-qkd`. A failing LOWTRAN native binary or invalid Gurobi license causes a clear startup failure; neither can be fixed just by reinstalling Python libraries.

## Historical ERA5 weather recovery

Weather data downloaded through Open-Meteo is converted to validated NetCDF, cached in `backend/data/era5/`, and identified by the file content and UTC date. Files named `<id>.nc` and `<id>.json` must be kept **together**. Dataset IDs in saved experiments refer to these files, not to a global Open-Meteo dataset service. A backend restart itself does not delete cached files.

When running an experiment, the UI first verifies its saved weather dataset ID against the *running* backend. If the original dataset is present, it is loaded from disk. If not, the UI visibly retrieves genuine ERA5 data for the selected day from Open-Meteo, updates the experiment's dataset ID, and then starts the simulation. This recovery requires internet access and can take time. **It may replace a missing user-uploaded NetCDF with Open-Meteo reanalysis for the same day**; retain the original NetCDF if precise source reproducibility is required. No fallback or fabricated physical rates are used.

To transfer experiments between installations, also copy `backend/data/era5/` (and re-upload trajectory files if the backend's trajectory registry was reset). An exported experiment JSON alone does **not** package cached weather or trajectory content.

## Project structure

```text
backend/
  .venv/                       # auto-created, excluded from distribution
  data/era5/                   # real weather files and manifests (preserved)
  .rate-cache.sqlite3          # physics calculation cache (preserved)
  balloon_qnet/                # original optical physics + native LOWTRAN7
  stratoq_demo/                # API models, physical setup, Gurobi allocators, weather
  tests/                       # backend regression tests
  main.py                      # FastAPI endpoints
  requirements.txt
frontend/
  src/                         # React editor and simulator views
  public/favicon.svg
  package-lock.json            # reproducible npm dependencies
scripts/check_backend.py       # scientific environment preflight
start-stratoq.sh               # integrated launcher
```

## Verify before a demonstration

```bash
./start-stratoq.sh --setup
STRATOQ_DEEP_PREFLIGHT=1 ./start-stratoq.sh --doctor
# Optional scientific tests, from the project root:
backend/.venv/bin/python -m pytest -q backend/tests
```

The deep preflight executes the native atmospheric model and confirms numerical channel results. For performance, a normal launch checks the native module loads and that a small Gurobi optimization completes, but does not run the full optical model twice. For additional notes, see [docs/ENVIRONMENT-AND-DATA.md](docs/ENVIRONMENT-AND-DATA.md).

## Important constraints

- The bundled native macOS LOWTRAN extension is for **CPython 3.10, arm64**; using Intel/Rosetta Python or another Python version requires a matching native rebuild. Do not overwrite it when installing Python dependencies.
- Local weather download work is sequential; Open-Meteo availability and licensing are external dependencies.
- The simulator has no authentication; keep its HTTP endpoints bound to localhost. It is designed for a local, trusted machine.
- The original physical model, Gurobi mathematical formulations, visualization, experiment data and rate cache have not been changed as part of this packaging/startup update.
