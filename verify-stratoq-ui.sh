#!/bin/sh
set -eu
cd "$(dirname "$0")"
for f in frontend/src/App.jsx frontend/src/styles.css frontend/index.html frontend/public/favicon.svg; do
  test -s "$f" || { echo "MISSING $f" >&2; exit 1; }
done
grep -q 'data-ui-build="1.0.7"' frontend/src/App.jsx || { echo 'App.jsx is not v1.0.7' >&2; exit 1; }
grep -q 'v1.0.7 — audit fix' frontend/src/styles.css || { echo 'styles.css is not v1.0.7' >&2; exit 1; }
grep -q 'favicon.svg?v=107' frontend/index.html || { echo 'index.html is not v1.0.7' >&2; exit 1; }
grep -q 'ellipse' frontend/public/favicon.svg || { echo 'favicon.svg does not contain atom orbits' >&2; exit 1; }
echo 'PASS: v1.0.7 frontend files installed in this directory.'
echo 'NEXT: cd frontend && npm run dev -- --force'
