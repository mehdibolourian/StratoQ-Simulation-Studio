# StratoQ Studio v1.0 — Historical ERA5 weather

## Installation and workflow

Apply the v1.0 patch to an **existing, working v0.9 installation**. The patch does not touch your locally compiled LOWTRAN native extension. The complete source archive intentionally omits all precompiled `.so` files; when used instead of the patch, LOWTRAN needs its local build described in `REAL-PHYSICS-V08.md`.

```sh
cd /Users/mehdi/Files/stratoq-studio
unzip -o ~/Downloads/stratoq-studio-v10-era5-patch.zip
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python -m uvicorn main:app --reload --port 8000
```

In a second terminal, start Vite as before (`cd frontend && npm run dev`), then hard-refresh Chrome. Both the API version and UI build should show `1.0.0`.

The left sidebar now has **Historical weather · ERA5**. Choose a **UTC date** and either:

1. Click **Load ERA5 from Copernicus** (requires a CDS account, accepted licence, internet and server-side API token), or
2. Click **Import local ERA5 .nc / CDS .zip** (a NetCDF file containing the required variables and spatial/temporal coverage).

Loading a dataset automatically enables historical mode. Press **Run simulation** to recompute physical link rates, storage and QKPs; progress includes ERA5 ray-sampling and the original Balloon-QNet theoretical channel. Playback creates, varies and removes the **read-only ERA5 weather cells**, while hand-placed weather objects remain separately editable and additive. Untick **Use ERA5 historical weather** to return to manual/static mode without deleting those manual objects.

On startup, the backend does **not** automatically contact CDS, and it never invents weather data. A failed CDS/NetCDF request produces an explicit error.

### Obtain a Copernicus CDS API token

Register/authorize at <https://cds.climate.copernicus.eu/>, accept the **ERA5 hourly data on single levels** licence, and configure `~/.cdsapirc` following <https://cds.climate.copernicus.eu/how-to-api>. Credentials remain on the backend Mac, never in the browser scenario. `cdsapi` is installed from backend requirements. Requests may queue remotely; the UI reports the current retrieval stage (CDS offers no trustworthy percentage while queued). First retrieval requests the selected UTC date and the following day; cached datasets are saved under `backend/data/era5/` (ignored by git) and reused across backend restarts.

ERA5 normally has a several-day publication delay; it is **historical reanalysis**, not live observations or a weather forecast. The geographical area is derived from the current GS/HAP locations and hourly samples of uploaded trajectories, expanded with a ~0.55° margin and aligned to 0.25° grid bounds. Data outside this area are not extrapolated: moving a node out of the cached region requires reloading ERA5.

### Required NetCDF fields and units

ERA5 **single-level** data, not the **50 hPa** wind NetCDF from the research project's old `update_coordinates('wind', ...)` helper:

| Field | ERA5 long name | Unit | Meaning |
|---|---|---|---|
| `tp` | Total precipitation | m of liquid water equivalent | Accumulated over previous UTC hour, valid at the interval END |
| `sf` | Snowfall | m of liquid water equivalent | Accumulated over previous UTC hour, valid at the interval END |
| `t2m` | 2m temperature | K | Instantaneous at the labelled hour |
| `d2m` | 2m dewpoint temperature | K | Instantaneous at the labelled hour |
| `lcc` | Low cloud cover | 0–1 | Instantaneous at the labelled hour |

A file must span **00:00 UTC on the selected date through 00:00 UTC the following date** and contain a minimum 2×2 spatial grid. Both negative/unphysical precipitation and missing/nonfinite data are rejected. For user-supplied NetCDF, *origin cannot be verified* merely by the presence of field names.

## Temporal/spatial treatment

ERA5 is hourly and approximately 0.25° spatial resolution (roughly 25–30 km at mid-latitudes). Selecting 10 s or 5 min time slots does not create new meteorological measurements.

For a time slot `[a,b)`, the accumulated precipitation values represent the **hour ending at the timestamp**. Convert each hourly total into mm/hour (multiply metres water-equivalent by 1000); the slot-mean rate is the **duration-weighted mean of overlapping hourly rates**:

```
R_slot [mm/h] = Σ_h (max(0, overlap([a,b), [h-1,h))) / (b-a)) × 1000 × tp[h]
S_slot [mm/h W.E.] = same calculation applied to sf[h]
Rain_slot = max(0, R_slot − S_slot)
Snow_slot = S_slot
```

This conserves integrated precipitation across a change in time-slot size, unlike direct linear interpolation of hourly accumulated totals. For instantaneous `t2m`, `d2m`, and `lcc`, the server linearly interpolates their gridded values at each time-slot **midpoint**; it performs bilinear interpolation between four spatial ERA5 grid points. The last slot is clipped to 24:00 UTC. The backend caps output to 1,500 frames (same as the previous app).

### Fog is an explicitly labelled diagnostic, not an observation

ECMWF provides the relationship `RH=e_sat(Tdew)/e_sat(T)` for near-surface relative humidity. The default diagnostic flags **fog-like conditions** when `RH ≥ 97%` and `lcc ≥ 70%`. These *thresholds are developer assumptions*, not an ERA5 fog product or measured visibility. To turn the flag into a link-loss hypothesis, it uses the user's StratoQ `helper.py` assumption **visibility V=0.5 km** and low-layer thickness **H_C=0.5 km**. It cannot resolve true fog patches or claim to measure visibility. Low-cloud cover alone is not classified as fog.

## Atmospheric link attenuation and realistic limits

For each GS–HAP ray and slot, the original Balloon-QNet `channel_theory` calculates the clear-sky optical efficiency (`LOWTRAN7`, turbulence, AO, optical tracking/coupling). That result remains cached by physical geometry and optical settings. Historical weather **does not replace or approximate the original physical model**: additional meteorological loss is integrated along the part of the 3D ray in the lower weather layers:

`L_ERA5 = Σ_i [γ_rain(R_i) + γ_snow(S_i,T_i) + I_fog,i γ_fog(V)] Δs_i`

Here the ray from ground to HAP is sampled at 12–40 midpoints between 0 and `min(5 km, HAP height)`. The precipitation-layer height **H_W=5 km** and fog-layer height **H_C=0.5 km** are sourced from the uploaded StratoQ `helper.py`; assuming uniform hydrometeor rates through these depths is an **explicit vertical-profile simplification**, not provided by single-level ERA5. The horizontal ERA5 field is sampled at the true optical-ray position; rendered weather circles are for presentation **only** and never reused for loss integration.

- **Rain:** `γ_rain = 1.076 R^0.67 dB/km` with `R` in mm/h — optical-FSO formula used by **ITU-R Report F.2106-1**, §4.1.2.1.
- **Snow:** `γ_wet = 3.95 S^0.72` or `γ_dry = 5.58 S^1.38 dB/km` with `S` in mm/h water-equivalent — cited in *2024 Narvik FSO snow measurements*, IEEE Access 2024. The current model uses interpolated **2m air temperature ≥ 0°C** as a **wet-snow proxy**, not confirmed snow microphysics. The study cautions these empirical models can be inaccurate elsewhere.
- **Fog:** `γ_fog = (3.91/V) (λ/550 nm)^(-q) dB/km`, with helper.py's `q(V)` piecewise rule, visibility `V` in km, and wavelength `λ` in nm. `V=.5 km` is an assumed parameter for the fog proxy.

Manual weather is calculated independently using the same documented fog visibility expression and the published optical rain/snow specific-attenuation laws, with editable radius/intensity/optional additional dB. Manual snow now offers an explicit **wet/dry** selector (default wet); unlike v0.9, its rain/snow intensity-to-attenuation law uses these published empirical fits, so numerical results will change. Total loss is **summed in dB** (manual + ERA5). The final channel efficiency is `η_total = η_balloon_qnet × 10^(−L_total/10)` and the BB84 SKR is computed by v0.8's existing secret-rate routine; the placeholder allocation then creates QKP storage. Manual and historical weather can describe the same storm, so manually duplicating a historical event deliberately double-counts attenuation; this is the requested additive override behavior.

**Research limitations:** ERA5 represents grid-box averages, not sub-grid measured storms; single-level ERA5 does not determine actual 3D hydrometeor vertical structure or fog visibility; wet/dry snow classification is approximate; published attenuation laws remain empirical fits with region-dependent uncertainty. This feature enables historically informed *scenario simulation*, not a fully validated physical meteorological reconstruction.

## Data/display separation and performance

`/api/era5/datasets/{id}/frame` previews the sampled **visual** weather cells without running expensive LOWTRAN. Each active grid cell appears as a small colored fog/rain/snow circle (up to **75 highest-intensity overlays** for performance); each particle effect varies with ERA5 weather intensity and naturally vanishes when below the display threshold (0.05 mm/h for precipitation). Underlying link physics samples the **full ERA5 grid** and integrates every nonzero intensity, even if not visualized. ERA5-generated regions cannot be dragged/edited; manual regions still can. The same frame data drive the UI time slider, 3D scene and map.

`backend/stratoq_demo/era5_weather.py` contains parsing, sampling, validation, geometry and display-layer generation. `era5_jobs.py` handles remote CDS retrieval. `physical_setup.py` attaches per-slot historical path loss and flags to the original physical link records. `resource_allocator.py` outputs rendered weather layers and authoritative link rates/QKPs. `main.py` exposes the new REST APIs.

### New endpoints

- `POST /api/era5/jobs` with `{"date_utc":"2026-01-10","scenario":{...}}`: queue a real CDS request.
- `GET /api/era5/jobs/{job_id}`: poll queue/download/parse status and retrieve the dataset ID on completion.
- `POST /api/era5/upload` multipart `date_utc`, `file`: import NetCDF or CDS ZIP.
- `GET /api/era5/datasets/{id}/frame?date_utc=...&slot_seconds=300&slot=0`: preview historical visualization at one slot.
- Existing `POST /api/simulations` and `/api/simulate` accept `scenario.config.weather_source="era5"`, `era5_date`, `era5_dataset_id`; historical mode requires a valid loaded dataset or returns an explicit error.

### References

1. [Copernicus CDS ERA5 hourly single-level dataset](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels) (ECMWF; documentation and downloads).
2. [ECMWF ERA5 accumulated/instantaneous parameter time conventions](https://confluence.ecmwf.int/pages/viewpage.action?pageId=111150607).
3. [ECMWF humidity calculation from 2m temperature and dewpoint](https://confluence.ecmwf.int/pages/viewpage.action?pageId=155343959).
4. [ITU-R Report F.2106-1 (2010)](https://www.itu.int/dms_pub/itu-r/opb/rep/r-rep-f.2106-1-2010-pdf-e.pdf), §4.1.2.1 rain attenuation.
5. [2024 field study of FSO snow attenuation](https://munin.uit.no/bitstream/handle/10037/35810/article.pdf?isAllowed=y&sequence=2), empirical wet/dry snowfall laws and limitations.
6. Supplied `helper(1).py`, constants `H_C`, `H_W`, `V_fog` and the fog attenuation coefficient; and supplied `setup(2).py` for StratoQ topology conventions.
