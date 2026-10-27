# StratoQ Studio v0.9 — adjustable weather intensity

## What changed

In the right-hand weather inspector (below the Fog/Rain/Snow buttons), the new *Weather intensity* panel includes:

- **Fog/cloud:** visibility in kilometres (lower visibility means stronger fog). New regions default to 0.5 km.
- **Rain:** liquid precipitation rate in mm/hour. New regions default to 5 mm/hour.
- **Snow:** *liquid-water equivalent* snowfall rate in mm/hour. New regions default to 5 mm/hour. This is NOT centimetres/hour of snow depth.
- **Radius:** remains independently adjustable. **Optional extra loss** remains available, defaulting to 0 dB for newly created regions.

The 3D particle count changes with rain/snow rate and fog visibility; rain/snow animation speed also changes. These are illustrative graphics, not particle-resolved physical simulation. Weather type, radius, and intensity update instantly in the scene; select **Run** to update numerical channel capacities and QKPs.

## Exact physical treatment in this revision

The original Balloon-QNet `channel_theory` still produces each *clear-air* channel efficiency, with all its original LOWTRAN, turbulence, and AO calculations. The weather overlay uses `backend/stratoq_demo/weather_physics.py`, which computes additional optical loss and multiplies the cached clear-air efficiency by `10^(-loss_db/10)` before converting to the BB84 rate. All affected time slots and their QKP states are recalculated on Run. The expensive clear-air calculations remain cached if only weather changes.

The uploaded StratoQ `helper.py` uses **visibility V**, not precipitation rate, and defines the following nominal specific loss coefficients in dB/km:

- Fog: `3.91/V * (lambda_nm/550)^(-q(V))`, using the usual visibility-dependent `q` branches in the helper.
- Rain: `2.8/V`, where `V` is atmospheric visibility in km.
- Snow: `58/V`, similarly.

There is **no measured precipitation-rate to visibility conversion** in the supplied helper. Thus this revision **does not claim to exactly reproduce the original precipitation-physics formula from mm/hour input**. Instead, it uses the helper's nominal rain and snow coefficients at **V=4 km**, and adds an explicitly *heuristic* intensity scaling:

- Rain `gamma = (2.8 / 4) * (rate_mm_h / 5)^0.67` dB/km.
- Snow `gamma = (58 / 4) * (rate_mm_h / 2)^0.8` dB/km.

For fog, gamma is directly determined by the user-supplied visibility. Rain and snow are 0 dB/km at 0 mm/h. Existing weather regions that do not specify the new intensity fields retain their previous fixed attenuation, ensuring backward compatibility.

### Atmospheric geometry

Weather is treated as a vertical circular-footprint atmospheric layer. The affected slant ray is clipped both to the circular horizontal footprint and to the atmosphere-layer altitude (fog 0.5 km; rain/snow 5 km, matching `helper.py`). The extra dB loss applies when the projected segment intersects the region, preserving the previous manual override.

### Assumptions and future research integration

This precipitation mapping is a **configurable demonstration model**, not validated attenuation across precipitation particle size distributions. It does not modify the intrinsic Balloon-QNet LOWTRAN transmittance, and may double count atmospheric effects if LOWTRAN is configured with overlapping meteorological conditions. For research-grade precipitation rates, replace `regional_weather_loss_db` with an experimentally grounded optical extinction model and expose the required microphysical parameters. This is independent of the authentic clear-air Balloon-QNet computation.

## Installation

From the project root, unzip the patch over the existing v0.8 tree. Restart FastAPI and Vite, then hard refresh. Confirm `/api/health` reports `0.9.0`. Run backend tests with `python -m pytest -q`.
