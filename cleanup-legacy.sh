#!/usr/bin/env bash
# Optional, for an older in-place installation. Moves known obsolete release
# notes, install verifiers, backup directories and payload copies to a safe
# sibling backup directory. Never touches .venv, node_modules, simulation source,
# original LOWTRAN files, saved experiments, physical-rate cache or weather data.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$(dirname "$ROOT")/stratoq-legacy-backup-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$DEST"
count=0
cd "$ROOT"
for item in *-UPDATE.md *-V*.md INSTALL-AND-VERIFY-V107.md LOGO-FIX-V109.txt WATERLOO-LOGO-INSTALL.txt '├å┬┐U╠ü╦ÿ.md' payload .ipynb_checkpoints .stratoq-*-backup-* verify-stratoq-ui.sh verify-stratoq-logo.sh verify-stratoq-v*.sh install-stratoq-offline-v116.sh; do
    if [ -e "$item" ]; then
        mv "$item" "$DEST/"
        count=$((count+1))
    fi
done
if [ "$count" = 0 ]; then rmdir "$DEST";echo 'No known legacy patch artifacts to archive.'
else echo "Moved $count legacy entries to: $DEST"; fi
echo 'Nothing in backend/data, backend/.venv, frontend/node_modules or balloon_qnet was moved.'
