# StratoQ Simulation Studio v1.1.5 — UI cleanup

This patch applies **on top of v1.1.4** and modifies only the frontend. Gurobi, SCAR-Q, MCR-Q, the offline optimizer, Open-Meteo, LOWTRAN and network simulation logic remain unchanged.

## Navigation

All four left sidebar groups and five right inspector groups are native `<details>` disclosures, closed initially:

| Left | Right |
| --- | --- |
| Workspace | Performance |
| Network elements | Selected object |
| Weather · ERA5 | Simulation |
| Scene objects | Physical channel |
| | System |

Solver details also have a nested closed disclosure in Performance. The heading of each section displays context (such as the selected object, current algorithm, current experiment, or satisfaction). Press its heading to expand or collapse it. The outer panels themselves are still resizable and collapsible.

## Reduced clutter

Removed the scenic explanatory sentence, overline, redundant live-view label, duplicate simulation-configuration link legend, redundant section explanations and persistent UI version badge. Export/import is now a compact `Files` dropdown, preserving all three actions. The current backend and calculation state remain available, but are more concise.

## Theme

Unified dark navy `#0B0F19`, panel `#111827`, card `#1E293B`, muted cyan `#58ABC8`, slate text, violet for special elements, emerald for healthy/connected states. Distinct animated link states (optical generation versus stored QKP) and warning/error colors remain semantic. The header icon and favicon use the same blue/cyan SVG. The official full University of Waterloo logo and the specified Networks Lab URL are preserved.

## Install

```bash
cd /Users/mehdi/Files/stratoq-studio
unzip -o ~/Downloads/stratoq-studio-v115-ui-cleanup-patch.zip
bash verify-stratoq-v115.sh
cd frontend
npm run dev -- --force
```

Hard-refresh Chrome. To confirm Vite is serving the new files, inspect the root `app-shell` element: it has `data-ui-build="1.1.5"`. The old visible UI version badge was deliberately removed.

## Validation and limitations

Source JSX was parsed using TypeScript's JSX parser, and the stylesheet was parsed with `tinycss2`. The verification script checks installed paths, essential controls, and branding. Full Vite compilation and actual Chrome rendering couldn't be executed in this environment because frontend packages were not available offline; browser visual verification is still needed.
