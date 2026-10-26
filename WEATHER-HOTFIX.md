# StratoQ Studio v0.6.1 — weather UI hotfix

Changes:
- Weather types are now three prominent buttons in the selected weather region's inspector: Fog / cloud, Rain, Snow.
- In 3D, enable Move (cursor icon) and drag the weather region's raised colored grab handle; the region ground disk can also be grabbed. Map mode still supports drag on the weather marker.
- Weather pointer handlers are on the entire weather group (including particles and boundary) to avoid pointer interception during drag.
- HTTP 500 is now described as an internal FastAPI error, not as an unavailable server. Check the FastAPI terminal traceback.

To apply: replace `frontend/src/App.jsx`, `frontend/src/components/Network3D.jsx`, `frontend/src/styles.css` or use this entire project folder. Restart Vite. Backend files are unchanged.

Backend verification: HTTP 200 for `/api/simulate` with fog, rain, snow in default scenario, and 10 pytest tests pass. The browser build was not verified because npm dependencies are unavailable in the execution environment.

If HTTP 500 persists, the backend terminal traceback is necessary to identify the local failure. Make sure the backend is the matching version from this archive and update dependencies using `python -m pip install -r requirements.txt`.
