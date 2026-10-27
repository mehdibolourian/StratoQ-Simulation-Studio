# StratoQ Studio v1.0.2 — CDS queue protection

## Why your October 27 CDS request was rejected

The CDS API responded with HTTP 400 and "Maximum number queued requests for this dataset has been reached. Please configure your scripts to request data sequentially". This is a **CDS service-side queue-limit rejection**. It is not a corrupt NetCDF, a large file, or evidence that cdsapi is missing. A separate issue in StratoQ Studio v1.0.1 was its `ThreadPoolExecutor(max_workers=2)`, which allowed two *different* UI jobs to submit CDS retrievals at once, even though each job sequentially downloaded its 24-hour day and next-day midnight sample.

ECMWF's Oct. 22, 2026 notice advises sequential requests and warns against repeated invalid or excessive requests: https://forum.ecmwf.int/t/data-stores-service-protection-measures-affecting-data-downloads-and-account-access-cds-ads-ewds-ecds/15481

## What is fixed

- Only one local ERA5 retrieval at a time (`max_workers=1` and atomic guard in `launch`).
- Repeated requests for the **same date and geographic bounds** return the running job; no new CDS request is submitted.
- A second different date or ROI returns HTTP 409 with an actionable error; it does not queue another CDS request in StratoQ.
- If CDS explicitly rejects a job due to its queue limit, the UI receives a short explanation. New local CDS submissions are paused for **10 minutes**, persisted on disk through backend restarts (HTTP 429), to avoid hammering the service. This is not an estimate of how long CDS queue congestion will last.
- On normal completion or non-quota failure, a new job is allowed. The per-day file cache and previous progress bar remain unchanged.
- Existing ERA5 NetCDF imports, daily cache, 25 timestamps (24 + next midnight), manual-weather addition, LOWTRAN/Balloon-QNet, and physical attenuation calculations are unchanged.

## Installation

Stop the backend with Ctrl+C. From project root:

```bash
cd /Users/mehdi/Files/stratoq-studio
unzip -o ~/Downloads/stratoq-studio-v102-era5-queue-guard-patch.zip
cd backend
source .venv/bin/activate
python -m pytest -q
python -m uvicorn main:app --port 8000
```

Run with **one worker and without `--reload`**, as before. Do not run a second instance of FastAPI pointing at the same CDS account. Existing compiled native LOWTRAN files are not included in the patch.

Before pressing Load ERA5 again, visit your CDS account's **Your Requests** page (CDS web UI) and check any outstanding requests from earlier tests. Let them finish; avoid repeatedly submitting new requests. The account-specific vs. dataset-wide share of the queue limit is not exposed in this error.

### Verification

`python -m pytest -q`: 51 tests passed offline. New tests cover duplicate-job reuse, denial of parallel UI jobs, HTTP 409 on busy, classification of the CDS queue-limit error, HTTP 429 cooldown, and survival of the cooldown across process restarts. CDS itself was not contacted by tests, so this patch cannot guarantee server acceptance while ECMWF's queue is full.
