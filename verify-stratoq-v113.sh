#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
grep -q 'data-ui-build="1.1.3"' frontend/src/App.jsx
grep -q 'resolveVisualLinks' frontend/src/components/Network3D.jsx
grep -q 'StoredKeyPulse' frontend/src/components/Network3D.jsx
grep -q 'No direct GS–GS route line' frontend/src/components/Network3D.jsx
node frontend/scripts/verify-link-states.mjs
echo 'PASS: v1.1.3 link-state visualization installed and regression checked'
