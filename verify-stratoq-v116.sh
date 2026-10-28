#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
test -f backend/stratoq_demo/offline_allocator.py || { echo 'FAIL: backend/stratoq_demo/offline_allocator.py missing'; exit 1; }
test -f backend/verify_offline_slot_scaling.py || { echo 'FAIL: slot-scaling verifier missing'; exit 1; }
python - <<'PY'
from pathlib import Path
p=Path('backend/stratoq_demo/offline_allocator.py').read_text()
assert 'discard_only_generated_' in p
assert 'discard_rate_' in p
assert 'offline_discarded_bits_total' in p
assert 'seconds * (capacity * activation[lid, t] - total_new\n                                         - total_old - discarded[lid, t])' in p
print('PASS: offline QKP overflow constraints installed')
PY
python -m py_compile backend/stratoq_demo/offline_allocator.py backend/verify_offline_slot_scaling.py
printf 'PASS: Python source compiles\n'
