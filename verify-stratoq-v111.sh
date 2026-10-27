#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python - <<'PY'
from pathlib import Path
alg=Path('backend/stratoq_demo/allocator_algorithms.py').read_text()
app=Path('frontend/src/App.jsx').read_text()
models=Path('backend/stratoq_demo/models.py').read_text()
assert 'def select_and_solve_slot(' in alg
assert 'rng.sample(list(scenario.demands)' in alg
assert 'n_trials = n_samples if algorithm' in alg
assert 'mcr_samples: int = Field(default=3' in models
assert 'MCR-Q · Monte Carlo routing' in app
assert 'data-ui-build="1.1.1"' in app
print('PASS: v1.1.1 Monte Carlo MCR-Q + greedy SCAR-Q files installed in this project.')
PY
