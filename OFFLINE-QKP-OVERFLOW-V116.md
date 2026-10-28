# StratoQ offline allocator — long-slot QKP-overflow fix (v1.1.6)

## Root cause

The old `offline_allocator.py` contained the QKP carryover constraint

    A[l,t+1] = A[l,t] + θ*(Kmax[l,t]*y[l,t] - fresh[l,t] - stored[l,t])

with `0 <= A[l,t] <= Amax[l]` and **no overflow/discard variable**. If a slot is long enough for the unused generation to exceed available storage, activating the link becomes impossible. For an initially empty QKP and constant demand at most `D`, if `θ*(Kmax - D) > Amax`, this forces `y=0` despite available physical capacity. A two-GS/one-HAP route then can be blocked, often driving served keys to zero at longer slots.

This is **not** a physical-rate cache-key problem. The physics cache keys depend on geometry/optical settings and may validly be reused across slot durations; the inconsistent behavior arises from the downstream storage MILP.

## Fix

Introduce nonnegative `discarded[l,t]` in **bits/s** and use

    A[l,t+1] = A[l,t] + θ*(Kmax[l,t]*y[l,t] - fresh[l,t] - stored[l,t] - discarded[l,t])
    0 <= discarded[l,t] <= Kmax[l,t]*y[l,t] - fresh[l,t]

This permits only **unused, newly generated** keys to be discarded. Previously stored keys remain subject to the existing start-of-slot availability constraint `θ*stored <= A[l,t]`. New generated keys cannot be used as old stored keys in the same slot. QKP remains bounded by `Amax`.

The patch also returns `offline_discarded_bits_total` in the run summary and `discarded_bits_total` in each slot's optimizer diagnostics (plus per-link `discarded_bits` in the internal result). These are diagnostics only and do not alter the objective, which remains total served keys.

## Install

Stop the backend, then from your **actual** StratoQ project root:

    cd /Users/mehdi/Files/stratoq-studio
    unzip -o ~/Downloads/stratoq-studio-v116-offline-qkp-overflow-fix.zip
    bash verify-stratoq-v116.sh

Restart FastAPI:

    cd backend
    source .venv/bin/activate
    python verify_offline_slot_scaling.py
    python -m pytest -q tests/test_offline_qkp_overflow_v116.py
    python -m uvicorn main:app --port 8000

The standalone checker runs **real Gurobi MILPs** (using a one-hour identical horizon, static links, 5 kbps generation, 4 kbps demand, 0.2 Mbit QKP capacity) at 10, 15, 30, 60 minutes; each should serve 14.4 Mbit. It does not require the physical-channel/LOWTRAN code, and checks that overflowing keys are actually discarded.

Then **click Run Simulation** in Studio (not timeline Play). The backend must reload the patched Python module. The visual frontend does not require a reinstall, and the backend `/api/health` version remains unchanged.

## Other diagnostics

- If longer-slot results remain worse after this patch, check that Gurobi status is `OPTIMAL` or is within the configured MIP gap, compare `horizon_seconds` and `total_requested_bits`, check physical link `capacity_bps` over the slots, and inspect time-varying weather/trajectories.
- A slot samples geometry/weather at its start, so reducing time resolution can still change the physical approximation; that is separate from the severe QKP overflow defect.
- For scientific results, use repeated comparisons at a fixed 24-hour horizon and report both served/requested keys and achieved MILP gap.
