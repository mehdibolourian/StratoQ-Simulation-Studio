# Topology and manual link failures update

## What's new

- Every ground-station/HAP pair is represented as a **potential optical link** (complete bipartite GS↔HAP graph).
- Newly added nodes show connections immediately, even before rerunning the simulator.
- Click a link in the 3D view or geographic map; the inspector provides a **Manually enabled** checkbox.
- Disabling a link persists as a scenario `link_overrides` entry and forces its generation rate to zero; the greedy allocator cannot route over it.
- Re-enable the link and rerun to restore eligibility. Failures are shown as muted red connections rather than disappearing.
- Out-of-coverage links are shown as potential connections with zero current capacity. Enlarging HAP coverage or moving nodes may make them feasible; manually enabling a link does not override physical range.
- Capacity and demand usage are only fresh after a simulator run; after edits, the UI shows **Run to calculate** instead of stale values.

## Run

Backend terminal:

```bash
cd stratoq-studio/backend
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

Frontend terminal:

```bash
cd stratoq-studio/frontend
npm install
npm run dev
```

Open http://localhost:5173 .  Click **+ Ground stations** or **+ HAP balloons**, click a connection, toggle **Manually enabled**, then click **Run StratoQ**.

## Simulator/schema distinction

`link_overrides` stores administrative link failures; candidate creation is separate from physical availability. Current optical rates, storage and routing remain synthetic demonstrations, not the actual StratoQ optimizer. A physically infeasible candidate has `in_range: false`, `active: false`, `capacity_bps: 0`. The backend remains authoritative for capacities and route availability. The frontend uses a quick spherical-distance approximation only for the immediate preview.

## Tests

`cd backend && python -m pytest -q`

Tests cover candidate pair completeness, out-of-range rates, weather, manual failure, re-enabling, and FastAPI round trip.
