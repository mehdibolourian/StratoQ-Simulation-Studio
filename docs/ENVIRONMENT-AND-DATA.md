# Environment and historical weather recovery

## Scientific environment

The reported SciPy `_vode` macOS dynamic loader failure came from Miniconda base's `site-packages`, not from a self-contained backend virtual environment. The launcher creates and uses `backend/.venv/bin/python`, explicitly verifies SciPy's compiled `_vode` module and its installation path, and checks that Gurobi can solve a small model before accepting simulations.

The provided native LOWTRAN file is `lowtran7.cpython-310-darwin.so` (arm64). A **Python 3.10 arm64** interpreter is required for this exact binary. Python 3.10 from Miniconda can be used only to *create* the isolated `.venv`; the launcher does not intentionally import packages from the base environment. If a corrupt `.venv` exists, the launcher renames it to `.venv-broken-<timestamp>` instead of deleting it.

## Persistent datasets

ERA5 NetCDF payloads and small JSON manifests live in `backend/data/era5`. A saved experiment's `era5_dataset_id` identifies **local file contents**; the ID cannot be resolved from Open-Meteo without a local copy. Both `<id>.nc`/`<id>.zip` and `<id>.json` must be preserved. A backend restart alone does not remove these files. In-process caches, however, are reset on restart and are reloaded from disk by the backend.

Before running an ERA5 experiment, the frontend checks that its exact saved dataset still exists. When the file is absent, the frontend visibly downloads a fresh ERA5 dataset for the selected UTC date from Open-Meteo and stores its *new* ID with the experiment. This requires internet access and may take a few minutes. **If the missing file was a user-uploaded NetCDF, it is not byte-for-byte recreated by Open-Meteo; restore the original file from backup for strict reproducibility.** No synthetic weather or approximate optical calculation is substituted.

The independent `backend/.rate-cache.sqlite3` stores reusable numerical channel efficiency values. It is not an ERA5 storage system. HAP trajectory uploads are registered in backend process memory and must be re-uploaded after restarting the API unless your saved experiment uses only static HAP positions.

## Checks

```
./start-stratoq.sh --setup
STRATOQ_DEEP_PREFLIGHT=1 ./start-stratoq.sh --doctor
./start-stratoq.sh
```

For separate terminals, use `./start-stratoq.sh --backend` and `./start-stratoq.sh --frontend`. The launcher refuses to silently fall back to the `hap-qkd` Jupyter environment and will not switch to an older FastAPI process already bound to port 8000.
