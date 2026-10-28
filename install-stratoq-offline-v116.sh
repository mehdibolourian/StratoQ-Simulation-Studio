#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -f backend/main.py || ! -d backend/stratoq_demo ]]; then
  echo "ERROR: Run this installer from the StratoQ project root (with backend/main.py)."
  exit 2
fi
if [[ ! -f payload/backend/stratoq_demo/offline_allocator.py ]]; then
  echo "ERROR: Payload missing. Extract the entire archive before installing."
  exit 2
fi
backup=".stratoq-offline-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
for file in backend/stratoq_demo/offline_allocator.py backend/diagnose_stratoq_optimal_scaling.py backend/verify_offline_slot_scaling.py; do
  if [[ -f "$file" ]]; then cp "$file" "$backup/$(basename "$file")"; fi
done
cp payload/backend/stratoq_demo/offline_allocator.py backend/stratoq_demo/offline_allocator.py
cp payload/backend/diagnose_stratoq_optimal_scaling.py backend/diagnose_stratoq_optimal_scaling.py
cp payload/backend/verify_offline_slot_scaling.py backend/verify_offline_slot_scaling.py
python -m py_compile backend/stratoq_demo/offline_allocator.py backend/diagnose_stratoq_optimal_scaling.py
export STRATOQ_EXPECTED_PATH="$(pwd)/backend/stratoq_demo/offline_allocator.py"
export STRATOQ_EXPECTED_SHA="151aa1b1724c08b821cad8301bf802d21d026f4bd930d1084ce02db82f9ff55c"
cd backend
python - <<'PYVERIFY'
import os, inspect, pathlib, hashlib
from stratoq_demo import offline_allocator as module
loaded=pathlib.Path(inspect.getfile(module)).resolve()
expected=pathlib.Path(os.environ['STRATOQ_EXPECTED_PATH']).resolve()
source=inspect.getsource(module.solve_offline)
actual_sha=hashlib.sha256(loaded.read_bytes()).hexdigest()
print('Imported module:',loaded)
checks={
  'Correct module location': loaded == expected,
  'Installed file matches package SHA256': actual_sha == os.environ['STRATOQ_EXPECTED_SHA'],
  'New discard constraint': 'discard_only_generated' in source,
  'New return field': 'offline_discarded_bits_total' in source,
}
for name, good in checks.items(): print(('PASS' if good else 'FAIL')+': '+name)
if not all(checks.values()): raise SystemExit(1)
PYVERIFY
printf '\nReinstall verified. Restart FastAPI to load the new Python module.\n'
printf 'Previous backend files backed up in: %s\n' "$backup"
