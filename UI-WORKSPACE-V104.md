# StratoQ Studio 1.0.4 — Workspace and UI polish

## Changes
- Removes prototype breadcrumb `Projects / Northern Ontario / Network editor` and dummy Local user avatar.
- Replaces the layered icon with an atom-inspired StratoQ logo/favicon.
- Adds subtle Waterloo gold accents and a Networks Lab / University of Waterloo development credit in the inspector footer. The `W` emblem is a **custom typographic mark**, NOT the official University of Waterloo crest. For official branding, source the approved colour-reversed horizontal logo from https://uwaterloo.ca/brand/uw-logos and follow their use rules.
- Multiple named experiment tabs: New, Duplicate, Rename (pencil), Switch and Close. Each tab keeps its own scenario, selection, and in-session simulation results.
- Scenarios are autosaved in this browser's localStorage. On reload, experiment scenarios are recovered; expensive simulation results must be re-run.
- Export scenario JSON (editable configuration), import a scenario JSON (as a new experiment).
- Export workspace JSON (all open experiment configurations) and import workspace JSON (replaces the current open workspace).
- Draggable left and right panel dividers and topbar collapse/expand buttons, with width preferences saved locally.
- Retains the Open-Meteo multi-coordinate elevation hotfix v1.0.3.1, backend weather retrieval, optical model, and LOWTRAN behavior.

## Import and export limitations
A scenario or workspace JSON saves the editable network setup and settings, but **does not bundle uploaded trajectory CSV data**, downloaded weather NetCDF grids, backend cache, or simulation results. Trajectory IDs and ERA5 dataset IDs refer to data stored in the backend installation. To move a demo to another machine, re-upload trajectories and retrieve/import ERA5 data there; otherwise, choose manual weather. To archive simulation outputs, use the inspector's export-results action separately.

## Installation
1. Stop the development frontend if running.
2. Extract the UI patch ZIP into the StratoQ project root, overwriting only the included frontend files. Do not erase the rest of the project.
3. Restart `npm run dev` in `frontend`.
4. Backend restart is unnecessary for this UI-only patch.

## QA
- TypeScript parser checked App.jsx syntax with JSX enabled.
- 56 Python backend regression tests passed.
- Browser UI manual QA and Vite production compilation could not be run in this environment (frontend npm dependencies unavailable without network access); test experiment switching, import/export and resizing in your browser.
