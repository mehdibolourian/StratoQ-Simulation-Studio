# StratoQ Studio v1.0.1 — ERA5 downloader reliability fix

## Root cause seen in the user's log

- CDS reached `successful` and began transferring a ZIP of only **86.0 kB**, then the local Uvicorn process repeatedly restarted because WatchFiles detected edits in Jupyter `.ipynb_checkpoints/*.py` files and `era5_jobs.py`.
- v1.0 stores download workers and job state **inside the Uvicorn process**. Auto-reload destroys the in-flight worker and loses job state; HTTP `200 OK` from `/api/era5/jobs/...` is only the frontend polling endpoint and does **not** mean CDS data are finished.
- v1.0 submitted **24 + 24 hourly samples** in two sequential CDS jobs and kept both responses in a temporary directory. Failure on the second day caused the successful first day to be re-downloaded.
- Occasional CDS connection failures remain possible; the logged DNS and read timeouts are separate transient network events, not evidence of a large downloaded file.

## Install without replacing the native Balloon-QNet / LOWTRAN build

From the root of your existing project:

```bash
cd /Users/mehdi/Files/stratoq-studio
unzip -o ~/Downloads/stratoq-studio-v101-era5-fix-patch.zip
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
# IMPORTANT: stop any old uvicorn instance first. Do not use --reload.
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Restart the frontend (if already running, Vite should detect changes), then refresh browser. The versions should both be **1.0.1**.

During ERA5 download, **do not change backend Python files or restart Uvicorn**. Once finished, you may restart it normally. The new downloader saves independent CDS daily files in `backend/data/era5/daily/`. An interrupted second-day request can be retried without re-downloading the first day. It also stores small status snapshots in `backend/data/era5/jobs/`; any incomplete job after a restart is reported as interrupted rather than appearing stuck.

## What changed

- Request 24 hours of the selected day plus ONLY next day's `00:00` sample: **25 timestamps** instead of 48. This maintains the existing correct interpolation/accumulation convention, which needs the next midnight.
- Cache each response by hash of CDS collection + exact request (date, variables, hours, bounding box, data format). Validate hourly timestamps and file decoding before caching. Never trust partially downloaded files.
- Use `cdsapi.Client(retry_max=3,sleep_max=10,timeout=120)` rather than up to 500 retries. `timeout` is a network-read timeout, not a bound on remote CDS processing.
- Show elapsed time, number of completed CDS requests (0/2, 1/2, 2/2), and bytes transferred *if* the CDS client writes a file incrementally. A moving indicator reflects indeterminate CDS queue/processing/transfer time; it is **not** a fabricated percentage.
- Save job metadata to durable files; report backend restart immediately if polling resumes in a different process.
- The rest of the ERA5 meteorology, manual weather overlays, link path geometry, Balloon-QNet numerical channel, and SKR calculation are unchanged.

## Limitations

CDS can still queue requests or experience slow data transfers. `cdsapi.retrieve()` does not expose a stable end-to-end total size or percentage; the UI correctly labels the step-based bar rather than inventing transfer completion. Running the backend with `--reload` still interrupts its worker; no patch can make an in-process Python thread survive process termination. The persisted daily results *do* survive.

The standalone StratoQ `helper.py` called `cdsapi.Client().retrieve()` for **one pressure-level wind product**, at 4 timestamps, and wrote a persistent file before use. Studio requests **five single-level precipitation/atmosphere fields**, makes two requests to preserve boundary-hour sampling, and runs them in an HTTP-server background thread. This patch fixes the extra request volume, persistence, and restart diagnostics rather than claiming the two workflows are identical.

## Test coverage

48 backend tests passed offline, including: 24+1 timestamp request semantics, per-request caching, fail-after-first-day + retry, persisted interruption status, ERA5 NetCDF parsing and physical-rate/QKP integration. These are synthetic fixture tests, not a live authenticated CDS retrieval. A frontend Vite build could not be run here because npm package installation was unavailable in this runtime.
