# StratoQ Studio v1.0.3.1 — Open-Meteo multi-point elevation hotfix

Fixes the Open-Meteo HTTP 400 error: `Parameter 'elevation' must have the same number of elements as coordinates`.

## Install
Stop FastAPI, then run from the existing StratoQ Studio project root:

```bash
cd /Users/mehdi/Files/stratoq-studio
unzip -o ~/Downloads/stratoq-studio-v1031-open-meteo-elevation-fix.zip
cd backend
source .venv/bin/activate
python -m uvicorn main:app --port 8000
```

The fix changes `_params()` so a batch of N coordinates has N `elevation=nan` values. This suppresses Open-Meteo elevation downscaling for each location. No physics, native binaries, or front-end code changed.

Offline regression checks: 56 backend tests passed. Live multi-location API request not performed.
