# StratoQ Studio v0.7 — analytical-capacity integration

## What is real and what is still a demo?

**Implemented:** GS/HAP/link/demand/system *objects* from the supplied `data.py` classes, sampled time-dependent HAP positions, spherical-Earth slant distance and elevation, pair-specific weather impacts, physical-parameter-dependent **analytical approximation** of BB84 secret-key capacity (bps), deterministic K_MAX for every directed link and slot, simulation frames populated with those rates, and dynamic QKP accounting using the resulting generated bits.

**Not implemented:** the original `calculate_key_rate_mac` algorithm from StratoQ, because its definition was **not provided** in `setup.py`, `data.py`, `libraries.py`, or `balloon_qnet.zip`. The original `balloon_qnet/transmittance_simulation.py` uses NetSquid even in its theoretical path, and its channel model includes detailed PDT, turbulence, AO and LOWTRAN calculations. The new `studio_analytical.py` is a deliberate **fast reduced-order approximation**, not an exact reproduction of the research model. Its values should **not** be used as validation or paper results. The allocator is a seeded-random/greedy **placeholder**, not StratoQ's optimizer. GS and HAP `N_RX/N_TX` limits are carried into the real objects but not yet enforced by the placeholder allocator. `A_MAX` is enforced by the QKP allocation of key storage budgets.

### Key files

- `backend/stratoq_demo/stratoq_data.py` — user-provided GS/HAP/link/system/demand classes, preserved as supplied.
- `backend/stratoq_demo/physical_setup.py` — builds all GSs/HAPs, two directed links per GS–HAP pair, `T`, `THETA`, `G`, weather/visibility arrays `W[t]`,`V[t]`, and `K_MAX[t]`. Exposes `create_physical_network(scenario)` and `calculate_key_rate_mac_analytical(...)`.
- `backend/balloon_qnet/` — included analytical package code and MIT license from user-provided archive. The NetSquid-dependent upstream modules remain available for future use, but are **not imported** by the web app.
- `backend/balloon_qnet/studio_analytical.py` — NetSquid-independent reduced Gaussian-beam model.
- `backend/stratoq_demo/resource_allocator.py` — uses physical K_MAX and simulates shared endpoint QKP inventories, random or greedy path selection.
- `backend/stratoq_demo/real_setup_bridge.py` — exports actual input constructor arrays and computed K_MAX for inspection.
- `frontend/src/App.jsx` — editable optical parameters, seeded routing selector, full per-slot link inspector.

### Physical model in this revision

For each GS–HAP link and time slot:

1. Geocentric spherical-Earth geometry computes slant range and ground elevation using WGS84-style geographic angles with a spherical Earth radius.
2. From wavelength `lambda`, waist `W0` and slant range `L`, propagate a diffraction-limited Gaussian beam: `w(L) = W0 sqrt(1 + (lambda L/(pi W0²))²)`.
3. Aperture collection `1-exp(-2(r_rx/w)²)`, obscuration, pointing loss, a simplified altitude-decaying atmosphere, and a **reduced-order turbulence/AO coupling penalty** determine the mean total efficiency. These are modeling assumptions and not the full NetSquid-free-space loss calculation.
4. Intersecting weather regions apply their UI-defined total excess loss in dB, `eta *= 10^(-loss_dB/10)`. The weather type is retained in `W[t]`; the UI region's dB is an externally chosen impairment. Weather path overlap uses the current 2D ground-projection geometry, not 3D cloud-volume propagation.
5. Asymptotic secret key rate: `R = source_rate * source_efficiency * eta * max(0,1 - 2 H2(QBER))`. Defaults match the values supplied in `transmittance_simulation.py`: 80 MHz, efficiency .01 and QBER .04.
6. There are separate uplink/downlink `K_MAX` arrays. For the current **one-edge-per-GS/HAP visual key pool** the allocator conservatively uses the smaller of the two directed link rates. This is a simplifying modeling choice and is not StratoQ's directed-resource allocation formulation.

The optical efficiency is a coarse model and has not been benchmarked against the original `calculate_key_rate_mac`. Rates will change deterministically with HAP trajectories, beam parameters, turbulence, receiver diameter, atmospheric visibility, manually disabled links and weather losses. Repeated simulation requests with the same scenario and allocator seed yield the same results.

### Run

```bash
cd stratoq-studio/backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python -m uvicorn main:app --reload --port 8000
```

In another terminal:

```bash
cd stratoq-studio/frontend
npm install
npm run dev
```

Visit `http://127.0.0.1:5173`, or `http://127.0.0.1:8000/docs` for API docs. The health endpoint `GET /api/health` must report version `0.7.0` and engine `analytical-bb84-approx`. Hard-refresh after replacing source files.

### Where to integrate actual StratoQ

Replace `calculate_key_rate_mac_analytical` in `physical_setup.py` with your actual implementation when you provide the module containing that function plus its dependencies. The generated `gs`, `hap`, `link`, `demand`, `system` objects already have the constructor data required by `init_setup_real_offline` and `init_setup_real_online`. Those original functions contain global state, plotting calls, and separate location update logic, so they should **not** be called directly from a web request; use this side-effect-free scene adapter instead. Reconcile `V`, `W`, channel model units and directed-link use when integrating.

### A demonstration check

With the default 2 GS, 1 HAP, 5-minute slots and 4 kb/s demand, dry-link K_MAX is around 7.5 kb/s (conservative bidirectional key pool), and QKP levels grow across frames until capacity limits are reached. Ten dB of weather loss cuts raw calculated link rates by about 90%. These are **approximation outputs**, not validated StratoQ figures.
