# Trajectory playback (v0.5)

Attach CSV/XLSX under **Inspector → select HAP → HAP trajectory**. Set **Time slot** in the playback deck and click **Play**. Uploaded trajectories are held in backend memory until restart; re-upload after restarting FastAPI.

Supported columns: `Time_s,Longitude_deg,Latitude_deg,Altitude_m` (CSV) and `time_s,lat,lon,alt` (first Excel worksheet). Time is seconds; altitude is metres; longitude 0–360° is converted to −180–180°. Interpolation is linear. Duplicate solver timestamps are skipped.

The shortest uploaded HAP trajectory determines the simulation horizon, rounded down to complete slots; static HAPs retain their chosen positions. A hard ceiling of 1500 frames prevents runaway browser responses (at 10 s over 24 h, only the first 1500 frames appear). Each slot invokes `scenario_at` and rebuilds the complete GS–HAP geometry before computing sample capacities/routing/QKP state. `frame.positions` updates the 3D scene and geographic map. These remain synthetic demo allocations, not StratoQ physical results.

Install updated backend dependency: `pip install -r backend/requirements.txt` from project root using your backend virtual environment. Run FastAPI and Vite as before.
