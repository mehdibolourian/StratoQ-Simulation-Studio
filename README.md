> **Learning Lab v1.2.2:** Network editing, topology-sized PPO, per-slot live monitoring and optional configurable curriculum are documented in [Learning Lab v1.2.2](docs/LEARNING-LAB-V122.md). The original Studio algorithms and optical code are unchanged.

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

## Learning Lab — topology-sized PPO (experimental)

The **Learning Lab** is a separate tab from the existing Network Studio simulation.
It starts a fresh actor–critic sized to the training topology, runs real masked
PPO updates, logs genuine reward / key-satisfaction measurements, and saves
frozen checkpoints and evaluation traces for playback in the existing 3D scene.
Its first controlled preset contains three Northern Ontario GSs, two HAPs, and
three GS-pair demands. Choose a short 12/24/48 five-minute-slot horizon and
an episode count; the default is 30 training episodes. Every episode calls
Studio's **existing genuine Gurobi slot LP**, using **Balloon-QNet-generated**
GS–HAP key rates cached before training. No approximate optical fallback or
synthetic reward values are used. Training demand magnitudes are randomized
within the explicitly documented range; evaluation is on a fixed demand
schedule and fixed geometry for interpretable checkpoint comparisons.

**Reproducibility boundary:** This is a *controlled training demonstration*,
not a reproduction of the paper's five simulated wind trajectories or held-out
real Stratotegic flight, three-topology, full-day evaluation. Heuristic-relative
training reward follows the shape of the paper's Eq. 14; the evaluation chart
shows actual served/requested key fractions. The initial version uses Studio's
existing per-slot Gurobi LP instead of directly importing notebook-only
`online_new` objects. For complete methodology and limitations, see
[docs/LEARNING-LAB.md](docs/LEARNING-LAB.md).

PyTorch is installed automatically in `backend/.venv` by `./start-stratoq.sh`
when Python requirements change. Never activate the `hap-qkd` notebook
Conda environment to run Studio. Training runs in a separate Python process;
its status, metrics, logs and checkpoint weights are persisted in
`backend/data/learning/<run-id>/`. Browser or FastAPI restarts do not erase
completed results, but stopping a detached old worker might require normal
OS process management.

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

## SciPy macOS zero-fill/dyld compatibility (Python 3.10)

Some recent macOS versions reject the Python 3.10 SciPy wheel's native
Mach-O sections with `section '__DATA/__thread_bss' has a zero-fill section
type, but offset field is not zero`. This is a binary packaging issue, not a
StratoQ atmospheric-model or Gurobi error. Reinstalling the same SciPy wheel
will reproduce it.

**Startup handles this narrowly**: only when the interpreter's scientific
library preflight reports that specific error on macOS, the launcher repairs
nonzero offsets in SciPy's Mach-O zero-fill section headers *inside*
`backend/.venv`, backs up each modified original in
`backend/.venv/.stratoq-native-backups/scipy/`, and re-signs modified files
with a local ad-hoc signature. It then repeats the scientific checks before
starting either service. This does **not** modify your Conda environments,
Gurobi, LOWTRAN, or StratoQ source models.

If macOS rejects code signing or a different binary fails validation, startup
stops and reports the problem; it does not keep reinstalling dependencies.
The native repair is a platform-specific workaround, not an upstream SciPy fix.
To check without changing files:

```bash
backend/.venv/bin/python scripts/repair_macos_scipy.py --check
```

The usual run command remains `./start-stratoq.sh`.


## v1.2.5 — Built-in experiment showcase

Network Studio now includes five reproducible experiments: matched SCAR-Q/MCR-Q/Optimal corridor scenarios and a paired Optimal QKP-on/QKP-off timed-storm demonstration. Use **Workspace → Built-in showcase experiments**, or **Replace tabs with showcase set** to replace previously saved examples. See `docs/BUILTIN-EXPERIMENTS-V125.md` for trace provenance, weather assumptions, controls, and limitations.

## v1.2.6 — Camera, Files, 24-hour flight and contextual timeline

Camera rotation now persists through moving-HAP playback while scene axes and framing remain adaptive. The Files button is again a properly styled dropdown. The paired QKP storm presets now use the original **full 24-hour CSV trace** (144 ten-minute slots); three algorithm-comparison presets deliberately remain at six hours because the May/June flight data uses high-altitude excerpts. Click the **Key moments** markers in the simulation timeline to inspect exactly which slots contain scheduled weather/demand changes and actual measured responses, with optional **Read more** context. Browser-saved five-hour tabs are preserved; open the new 24-hour preset from the update notice rather than overwriting them. See `docs/BUILTIN-EXPERIMENTS-V126.md`.
