#!/usr/bin/env bash
# File-layout validation; does not install anything or require Gurobi.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
for path in start-stratoq.sh start-stratoq-backend.sh start-stratoq-frontend.sh scripts/check_backend.py backend/main.py backend/requirements.txt backend/stratoq_demo/offline_allocator.py backend/stratoq_demo/open_meteo_jobs.py backend/balloon_qnet/lowtran_piccia/lowtran7.cpython-310-darwin.so frontend/src/App.jsx frontend/public/favicon.svg frontend/package-lock.json; do
    if [ ! -f "$path" ]; then echo "FAIL: required file missing: $path" >&2; exit 1; fi
done
bash -n start-stratoq.sh
if [ ! -d backend/data/era5 ]; then echo 'FAIL: ERA5 cache directory absent.' >&2; exit 1; fi
python_for_check=''
for exe in python3 python; do
    if command -v "$exe" >/dev/null 2>&1; then python_for_check="$exe"; break; fi
done
if [ -n "$python_for_check" ]; then
    "$python_for_check" - <<'PY'
from pathlib import Path
root=Path('backend/data/era5')
files=list(root.glob('*.nc'))+list(root.glob('*.zip'))
missing=[]
for f in files:
    if not (root / (f.stem + '.json')).is_file(): missing.append(str(f))
if missing: raise SystemExit('FAIL: dataset files missing their metadata manifests: '+', '.join(missing))
print(f'PASS: {len(files)} persisted ERA5 file(s) have matching manifest(s).')
PY
fi
printf '%s\n' 'PASS: cleaned StratoQ file layout and startup scripts.'
printf '%s\n' 'Next: ./start-stratoq.sh --setup  (creates backend/.venv and installs dependencies if needed)'
