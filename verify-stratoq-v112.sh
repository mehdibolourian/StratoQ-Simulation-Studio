#!/bin/sh
set -eu
for f in backend/stratoq_demo/allocator_algorithms.py backend/stratoq_demo/resource_allocator.py backend/stratoq_demo/models.py backend/verify_allocator_runtime.py frontend/src/App.jsx frontend/src/components/Network3D.jsx frontend/src/styles.css; do
    if [ ! -f "$f" ]; then echo "FAIL: missing $f; run from project root"; exit 1; fi
done
grep -q 'candidate_solves' backend/stratoq_demo/allocator_algorithms.py
grep -q 'Gurobi Allocation\|GUROBI ALLOCATION' frontend/src/App.jsx
grep -q 'data-ui-build="1.1.2"' frontend/src/App.jsx
grep -q 'function MovingPhoton' frontend/src/components/Network3D.jsx
echo 'PASS: v1.1.2 solver auditing and photon animation source installed in this project.'
