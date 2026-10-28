#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
for f in backend/stratoq_demo/offline_allocator.py backend/stratoq_demo/demand_profiles.py backend/stratoq_demo/resource_allocator.py frontend/src/lib/demandProfiles.js frontend/src/App.jsx frontend/src/styles.css; do
  test -s "$f" || { echo "MISSING: $f"; exit 1; }
done
grep -q 'data-ui-build="1.1.4"' frontend/src/App.jsx
grep -q 'total_requested_bits' backend/stratoq_demo/resource_allocator.py
grep -q 'optimality_gap' backend/stratoq_demo/offline_allocator.py
grep -q 'simulationHorizonSeconds' frontend/src/lib/demandProfiles.js
python -m py_compile backend/stratoq_demo/{demand_profiles,offline_allocator,models,resource_allocator,physical_setup}.py
if command -v node >/dev/null; then
  (cd frontend && node --input-type=module -e "import {slotCount} from './src/lib/demandProfiles.js'; const s={config:{slot_seconds:10},balloons:[]};if(slotCount(s)!==8640)process.exit(2);")
fi
echo 'PASS: StratoQ v1.1.4 demand patterns, full-day horizons, offline MILP and UI source installed.'
