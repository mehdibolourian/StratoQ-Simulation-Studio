#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
s=Path('frontend/src/App.jsx').read_text()
c=Path('frontend/src/styles.css').read_text()
index=Path('frontend/index.html').read_text()
svg=Path('frontend/public/favicon.svg').read_text()
checks={
 'UI 1.1.5 build marker': 'data-ui-build="1.1.5"' in s,
 'Collapsible sidebar sections': s.count('<details className="inspector-section collapsible-block')==5 and s.count('<details className="section-pad')==4,
 'Sections closed by default': 'className="inspector-section collapsible-block" open' not in s and 'className="section-pad collapsible-block" open' not in s,
 'Nested solver detail disclosure': 'className="solver-detail-disclosure"' in s,
 'Compact File menu': 'className="header-file-menu"' in s,
 'Editable weather type': '<span>Weather type</span>' in s,
 'No redundant title prose': 'Explore optical links and key-buffer dynamics' not in s,
 'Navy/cyan theme': '--sq-bg:#0b0f19;' in c and '--sq-accent:#58abc8;' in c,
 'Stylesheet matches UI build': 'data-ui-build="1.1.5"' in c,
 'Consistent favicon and header': '/favicon.svg?v=115' in s and '/favicon.svg?v=115' in index and 'ellipse' in svg,
 'Official Waterloo logo preserved': 'universityofwaterloo_logo_horiz_rev.png' in s,
 'Networks Lab link preserved': 'https://rboutaba-cs.github.io/watqkd/' in s,
}
for name,ok in checks.items():print(('PASS' if ok else 'FAIL')+': '+name)
if not all(checks.values()):raise SystemExit(1)
print('PASS: StratoQ Studio v1.1.5 UI patch installed in this directory.')
PY
