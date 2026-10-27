# StratoQ Studio v1.0.3 — Historical ERA5 through Open-Meteo

This release **replaces the in-app historical ERA5 downloader's Copernicus CDS request path with Open-Meteo's Historical Weather API**. No CDS account, `.cdsapirc`, or `cdsapi` is needed for the new download button. The legacy `era5_jobs.py` implementation remains in the repository for reference, **but the running FastAPI endpoints now use Open-Meteo**.

## Installation — patch into your existing local source

The patch contains only the files changed from Studio **v1.0.2** and is recommended for an existing Mac environment containing a working native LOWTRAN7 extension. It intentionally contains **no** Fortran, `.so`, `.dylib`, native binary, or `balloon_qnet` files.

1. Stop the running backend (`Ctrl+C`) and Vite server.
2. From the existing Studio root, extract the patch into that folder:

```bash
cd /Users/mehdi/Files/stratoq-studio
unzip -o ~/Downloads/stratoq-studio-v103-open-meteo-patch.zip
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

3. In the other terminal:

```bash
cd /Users/mehdi/Files/stratoq-studio/frontend
npm run dev
```

4. Open http://127.0.0.1:5173. In **HISTORICAL WEATHER · ERA5**, select `2024-10-15` and click **Load ERA5 from Open-Meteo**.

If you extract the **full archive**, place it in a separate folder first. The source archive does not contain your locally compiled LOWTRAN extension; retain the one in your existing installation.

## How it works

- `POST /api/open-meteo/jobs` submits a backend weather job; `GET /api/open-meteo/jobs/{id}` shows sequential-batch progress. The old `/api/era5/jobs` URLs are retained as aliases to the **new Open-Meteo downloader**, not as separate CDS requests.
- Selects a 0.25° grid covering the current GS/HAP topology, including sampled HAP trajectories and a 0.55° margin. This is **not an Ontario-wide 2020–present archive**; only the selected date and topology region are requested.
- Calls `https://archive-api.open-meteo.com/v1/archive` using `models=era5`, `timezone=GMT`, `cell_selection=nearest`, and `elevation=nan` to avoid the ordinary land/elevation downscaling. Each request contains at most **20 coordinates**, made sequentially in a single worker. No hidden synthetic weather data is substituted.
- Retrieves the selected UTC date *and the next day* to cover 00:00 to next-day 00:00 (25 samples), including the final precipitation accumulation. It checks all **48 returned timestamps** for the two-day interval.
- Validates units, coordinates, missing values, expected time samples, and a complete rectangular grid. If the provider returns something incompatible, it fails clearly rather than constructing an incorrect grid.
- Converts Open-Meteo fields into the existing ERA5 NetCDF schema, then loads through the **unchanged existing ERA5Cube and StratoQ ray-attenuation code**:

| Open-Meteo input | Studio field | Conversion |
|---|---|---|
| `temperature_2m` in °C | `t2m` in K | Add 273.15 |
| `dew_point_2m` in °C | `d2m` in K | Add 273.15 |
| `precipitation` in mm/hour accumulation | `tp` in metres water equivalent | Divide by 1000 |
| `snowfall` in cm/hour snowfall depth equivalent | `sf` in metres water equivalent | Divide by 7000 (Open-Meteo's 7 cm snow = 10 mm SWE) |
| `cloud_cover_low` in % | `lcc` fraction | Divide by 100 |

**Scientific limitation:** Open-Meteo's snowfall field is converted using a **fixed snow-to-water ratio**, so it may not precisely reproduce the original CDS `sf` variable; Open-Meteo values can also be processed and rounded. Do not claim bitwise identity with the official ERA5 NetCDF. The existing fog inference remains a humidity/low-cloud-cover **proxy**, not direct visibility measurements.

Each successful multi-location response batch is cached on disk under `backend/data/era5/open_meteo_parts/`. The fully validated day is stored in `backend/data/era5/`, using the existing ERA5 dataset registry. Retrying after a network failure reuses completed batches. A different selected day or changed topology may require new queries.

## What is unchanged

- Existing numerical physics in `backend/balloon_qnet` and native LOWTRAN7 binary.
- Existing `era5_weather.py` processing, including bilinear interpolation, rate-integrated precipitation, rain/snow/fog loss, 3D weather overlays, manual-weather addition, and time-slot settings (except added provenance metadata).
- ERA5 NetCDF/ZIP upload option and all simulation settings.
- The old `era5_jobs.py` source is retained but no longer called by the Studio weather UI.

## Validation

At package creation, **55 offline backend tests passed**. New tests use representative *mocked* Open-Meteo multi-location responses to verify 25 hourly samples, 0.25° gridding, unit conversions, expected precipitation split, repeat-request caching, API status responses, and explicit failure on invalid units or shifted coordinates. The user's earlier independent single-point Open-Meteo test did reach the real API and succeeded, but **this specific new Studio multi-location request path was not executed against the live Open-Meteo API** in the isolated packaging environment. If a real request reports a coordinate mismatch or provider rate limit, share the backend error and do not bypass the validation checks.

Documentation:
- https://open-meteo.com/en/docs/historical-weather-api
- https://open-meteo.com/en/features
