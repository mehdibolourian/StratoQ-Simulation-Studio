#!/bin/bash
set -e
cd "$(dirname "$0")"
test -f frontend/public/favicon.svg || { echo 'FAIL: missing frontend/public/favicon.svg'; exit 1; }
grep -q 'src="/favicon.svg?v=109"' frontend/src/App.jsx || { echo 'FAIL: top-left logo does not use favicon.svg'; exit 1; }
grep -q 'href="/favicon.svg?v=109"' frontend/index.html || { echo 'FAIL: browser favicon mismatch'; exit 1; }
grep -q 'waterloo-logo-full' frontend/src/App.jsx || { echo 'FAIL: full Waterloo logo missing'; exit 1; }
echo 'PASS: header logo and tab icon share frontend/public/favicon.svg; full Waterloo logo retained.'
