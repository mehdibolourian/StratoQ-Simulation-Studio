# StratoQ Studio v0.6 — setup fields and spatial weather

This update is based on uploaded `setup.py` and `data.py` (the actual StratoQ classes), **not** a working integration of the full StratoQ solver.

## Updated inspector

- GS: longitude, latitude, `N_RX`, `N_TX`, `A_MAX` (QKP max), tag/name.
- HAP: the same fields plus altitude, coverage, optional trajectory CSV/XLSX; the time-indexed longitude, latitude and H arrays are sampled from that trajectory.
- GS–HAP pair: enabled/disabled, `V` visibility in km (currently a per-pair constant), optional placeholder link capacity cap, current per-slot `W=(fog,rain,snow)` and calculated demo capacity. Every pair continues to be generated automatically.
- Weather region: effect (fog/cloud, rain, snow), center lat/lon, radius in km, illustrative extra path loss in dB. Drag its marker in MapLibre, or enable the Move tool and drag the disk in the 3D view. Three.js uses different illustrative particle styles for each effect.

## How weather is calculated

At each time slot the backend samples HAP trajectories before evaluating weather. `weather_by_hap[hap_id]` becomes one-hot-ish flags (`fog`, `rain`, `snow`) based on whether the HAP ground projection is within a region's radius. Multiple overlaps can set multiple flags.

For links, every weather circle intersecting the **2D ground projection** of the GS–HAP optical path contributes to `W[t]=(fog,rain,snow)` and adds the region's illustrative dB loss. A HAP can therefore have weather flag 0 while its optical beam intersects a patch elsewhere. `weather_by_hap` and the link flags are deliberately distinct. This is NOT yet full volumetric ray/cloud interception (there is no modeled vertical cloud profile).

## Real StratoQ interface

`backend/stratoq_demo/real_setup_bridge.py` exposes `to_real_setup_payload(scenario)`, preparing field arrays matching uploaded constructors:

```
GS(lg, la, N_RX, N_TX, A_MAX, tag)
HAP(lg[t], la[t], H[t], N_RX, N_TX, A_MAX, tag)
LINK(n1, n2, V[t], W[t], K_MAX[t])
system(T, THETA, G)
```

The adapter normalizes `lon` from signed degrees to StratoQ's 0–360 coordinates, creates both link directions, and includes per-slot weather arrays. `K_MAX_placeholder` is only a nominal bound; it is **not** output from your quantum physical layer.

**Integration gap:** In the uploaded `init_setup_real_offline/online`, `calculate_key_rate_mac` receives *global* fog/rain/snow arrays, not per-link `W[t]` as separate channel conditions. Before using spatial heterogeneous weather with real rates, that physical routine must be updated to consume the per-link flags or masks explicitly. The sample backend currently uses the extra dB loss as an illustrative weather adjustment. Node `N_RX/N_TX` is serialized but not enforced by the greedy demo allocator; the real resource allocator must enforce terminal-count constraints. `V` is preserved in the bridge but is not yet a physically parameterized visibility attenuation model.

The original research `setup.py` / `data.py` are not executed by the prototype. Their top-level dependencies and plotting/solver steps require independent integration.

## Running

Backend:

```
cd stratoq-studio/backend
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
python -m uvicorn main:app --reload --port 8000
```

Frontend (separate terminal):

```
cd stratoq-studio/frontend
npm install
npm run dev
```

Click a weather region in the map, choose Rain or Snow, drag/re-size it, then press Play to rerun the placeholder simulation. In the backend, `to_real_setup_payload(scenario)` may be invoked to inspect the complete StratoQ-shaped arrays without actually calling StratoQ.
