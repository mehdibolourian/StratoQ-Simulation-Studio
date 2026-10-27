# StratoQ Simulation Studio v1.0.5 UI patch

- Replaces the generated W with an actual University of Waterloo official horizontal reversed logo **loaded from uwaterloo.ca**. An internet connection is needed to display it; alternatively download the official image from the University Brand site and host it locally in `frontend/public`. University logo usage remains subject to Waterloo branding guidelines.
- Favicon now matches the header atom symbol. Browser caching may require a hard refresh.
- Restyles key actions/selection elements with Waterloo yellow while preserving physical data visualization colours and warnings.
- Both UI and API report 1.0.5, eliminating the false version-mismatch warning after installing BOTH patched files and restarting the backend.
- Adds space and separator between Simulation Config and Physical Channel.
- Changes scenario export/import wording to Experiment; Workspace is the collection of multiple Experiments. Existing legacy scenario JSON files still import.
- Sets header title to StratoQ / SIMULATION STUDIO on two lines.

## Install
Stop FastAPI and Vite; extract zip at project root. Restart FastAPI and Vite, and hard-refresh Chrome.
