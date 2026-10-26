# v0.8 — Actual balloon_qnet theoretical channel, parallel execution and progress

**No synthetic fallback.** `backend/stratoq_demo/real_rates.py` evaluates the
original upstream `transmittance_simulation.channel_theory` function, including
LOWTRAN7 atmospheric transmission, the original uplink/downlink turbulence,
AO, aperture and fiber coupling numerical routines. Rates are computed using
the source's BB84 SKR equation with user-specified source repetition, efficiency
and QBER. A user-authored spatial weather zone adds its editable attenuation
(dB) to the **channel efficiency** for intersecting optical paths. Original
`helper.py` has been preserved in `backend/research_reference/helper_original.py`.

## Dependencies — macOS

```bash
cd /Users/mehdi/Files/stratoq-studio/backend
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
python verify_physics.py
python -m pytest -q
python -m uvicorn main:app --reload --port 8000
```

The original archive contains a compiled `lowtran7.cpython-310-darwin.so`
for **Apple Silicon + CPython 3.10**. On precisely that ABI, this can be loaded
directly. Other Python versions must build LOWTRAN7 for their environment:

```bash
brew install cmake gcc       # includes gfortran
# For Python 3.12 and later:
python -m pip install meson meson-python ninja
python verify_physics.py
```

If the actual LOWTRAN model cannot load, the job **fails visibly** and the
FastAPI terminal records the traceback. No synthetic channel is used.

## Execution

1. On **Run** or Play when the scenario has unsimulated changes, the browser
   POSTs the current scenario to `/api/simulations`. The backend queues a job
   (instead of holding a request open for minutes).
2. `physical_setup.create_physical_network` samples uploaded HAP trajectories,
   constructs the original `gs`, `hap`, `link`, `demand` and `system` objects,
   and computes geographic slant ranges and per-slot weather intersections.
3. `real_rates.calculate_key_rate_mac_real` checks a persistent SQLite disk
   cache (`backend/.rate-cache.sqlite3`). **Keys include direction, slant
   distance, altitude, AO order, all optical inputs, and hashes of original
   physical model source files.** Unchanged link/slot efficiencies are reused;
   only missing unique geometry/direction cases call real `channel_theory`.
4. A `ThreadPoolExecutor` computes missing cases in parallel (configurable
   workers, default 10). A lock protects the non-reentrant native LOWTRAN
   Fortran calls, while SciPy channel calculations can overlap.
5. Downstream source, QBER, per-link weather attenuation and link overrides
   are applied, and calculated bidirectional K_MAX arrays feed the unchanged
   seeded-random/greedy demonstration allocator and QKP state animation.
6. The frontend polls `/api/simulations/{id}` for **total**, **completed**,
   **computed**, **cached**, and **workers**, showing actual progress. Results
   are returned by `/api/simulations/{id}/result` only on success.

## Important modeling boundaries

- This is the **original analytical/theoretical channel**, not NetSquid's
  event-based `channel_simulation`; NetSquid itself is not required. The base
  `QuantumErrorModel` needed by upstream channel classes is replaced with a
  small compatible property container **only**; all upstream mathematical
  calculation methods are retained. NetSquid event simulation will fail
  explicitly if called.
- The original `helper.py` branches for `fog`, `rain`, `snow` used weather in
  its PLOB calculation, but ignored the weather flags in the `theoretical`
  branch. Studio adds per-link dB attenuation at efficiency level based on
  intersecting **2D ground-projection** weather regions. A future extension
  could use 3D storm volumes and wavelength-physical scattering models.
- A GS↔HAP visual pair uses the **minimum of uplink and downlink SKRs** as
  its shared key-generation rate; it is not an optimized asymmetric protocol.
- Allocation and demand routing remain **demo placeholders**. Rates and
  their dependencies are real upstream numerical results, not placeholders.
- A change to an already cached **demand** or **weather overlay** generally
  needs no new LOWTRAN computations; changed GS/HAP geometry, altitude,
  optics or AO parameters invalidate the corresponding physical cache entries.
- If the backend is restarted while a job runs, the in-memory job state is
  lost and the browser will show a job-not-found error; completed physical
  evaluations are retained in SQLite cache. Use one Uvicorn worker.
- `python -m pytest -q` uses fixed atmospheric transmittance in tests to
  isolate and exercise the original numerical channel and caching when a
  native LOWTRAN binary is not available. **`python verify_physics.py` is the
  strict end-to-end smoke test of real LOWTRAN** on the target computer.

## Diagnostics

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/physics/status
python verify_physics.py
```

Do not delete `.rate-cache.sqlite3` unless you intentionally want to force a
cold full-channel recalculation. To benchmark a cold run, stop FastAPI and
remove the file, then restart and press Run.
