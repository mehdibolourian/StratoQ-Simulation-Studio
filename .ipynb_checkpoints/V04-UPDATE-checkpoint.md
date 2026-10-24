# v0.4 — Compact annotations and Play-to-recalculate

- Node annotations now show `GS · name` / `HAP · name` and `QKP NN%` in one compact row. Hover the label for the full QKP balance; use the inspector for detailed data.
- Link tags now show `capacity / used` in a compact single line (e.g. `15.4 kbps / 9.0 kbps`). OFF means manually disabled, OOR means out of range. Select the link to see detailed capacity and usage.
- Link tags use a smaller camera-distance scaling factor; all possible links are still shown.
- After any scenario edit, clicking Play reruns the FastAPI sample simulator on the latest scenario, waits for its response, resets the slot to zero, then starts playback. Run simulation remains available for manual refresh.
- Requests for out-of-date scenarios are ignored if the scenario changes during a request. If the backend fails, the UI shows an error and does not play stale results.
- No changes to the Python backend were needed. The adapter is still the sample simulator, not real StratoQ physical modeling.

## Install / run

Backend: `cd backend && source .venv/bin/activate && python -m uvicorn main:app --reload --port 8000`

Frontend: `cd frontend && npm install && npm run dev`

## Tests

Backend: `cd backend && python -m pytest -q` (5 passed at packaging). Browser/npm build not verified in this environment.
