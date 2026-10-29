#!/usr/bin/env bash
# StratoQ Studio macOS launcher: no shell activation required; macOS Bash 3.2 compatible.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"
PY="$VENV/bin/python"
MODE="${1:---all}"
case "$MODE" in --all|--backend|--frontend|--setup|--doctor) ;; *) echo 'Usage: ./start-stratoq.sh [--all|--backend|--frontend|--setup|--doctor]' >&2; exit 2;; esac

is_python_310() { "$1" -c 'import sys;sys.exit(0 if sys.version_info[:2] == (3,10) else 1)' >/dev/null 2>&1; }
select_python() {
    if [ -n "${STRATOQ_PYTHON:-}" ]; then
        if is_python_310 "$STRATOQ_PYTHON"; then printf '%s\n' "$STRATOQ_PYTHON"; return; fi
        echo "ERROR: STRATOQ_PYTHON is not a working Python 3.10 executable: $STRATOQ_PYTHON" >&2; return 1
    fi
    for candidate in /opt/miniconda3/bin/python3.10 /opt/miniconda3/bin/python3 python3.10 python3; do
        if command -v "$candidate" >/dev/null 2>&1 && is_python_310 "$candidate"; then
            command -v "$candidate"
            return
        fi
    done
    echo 'ERROR: Python 3.10 not found. Set STRATOQ_PYTHON=/absolute/path/to/python3.10.' >&2
    return 1
}
valid_venv() {
    [ -x "$PY" ] && "$PY" -c 'import sys, pathlib; p=pathlib.Path(sys.prefix).resolve(); expected=pathlib.Path(sys.argv[1]).resolve();sys.exit(0 if sys.version_info[:2]==(3,10) and p==expected else 1)' "$VENV" >/dev/null 2>&1
}
requirements_hash() { shasum -a 256 "$BACKEND/requirements.txt" | awk '{print $1}'; }
preflight() {
    if [ "${STRATOQ_DEEP_PREFLIGHT:-0}" = '1' ]; then
        (cd "$BACKEND" && "$PY" "$ROOT/scripts/check_backend.py" --deep)
    else
        (cd "$BACKEND" && "$PY" "$ROOT/scripts/check_backend.py")
    fi
}
check_free_port() {
    "$PY" - "$1" <<'PYCHECK'
import socket, sys
port=int(sys.argv[1])
sock=socket.socket()
sock.settimeout(0.3)
try:
    taken = sock.connect_ex(('127.0.0.1', port)) == 0
finally:
    sock.close()
if taken:
    print(f'ERROR: port {port} already has a server. Stop the old FastAPI/Vite process first.', file=sys.stderr)
    sys.exit(1)
PYCHECK
}
create_venv_if_needed() {
    if valid_venv; then return; fi
    local_source="$(select_python)"
    if [ -e "$VENV" ] || [ -L "$VENV" ]; then
        backup="$BACKEND/.venv-broken-$(date +%Y%m%d-%H%M%S)-$$"
        echo "Existing .venv is unusable; preserving it at $backup" >&2
        mv "$VENV" "$backup"
    fi
    echo "Creating isolated backend/.venv with $local_source"
    "$local_source" -m venv "$VENV"
    valid_venv || { echo 'ERROR: new .venv cannot execute Python 3.10.' >&2; exit 1; }
}
setup_backend() {
    create_venv_if_needed
    desired="$(requirements_hash)"
    installed="$(cat "$VENV/.stratoq-requirements-sha256" 2>/dev/null || true)"
    if [ "$installed" != "$desired" ]; then
        echo 'Installing/updating backend dependencies into the isolated project .venv ...'
        "$PY" -m pip install -r "$BACKEND/requirements.txt"
        printf '%s\n' "$desired" > "$VENV/.stratoq-requirements-sha256"
    fi
    # On macOS, verify the archived LOWTRAN7 extension before importing it.
    # This avoids a Gatekeeper dialog when a downloaded project carried quarantine.
    if [ "$(uname -s)" = 'Darwin' ]; then
        lowtran_native="$BACKEND/balloon_qnet/lowtran_piccia/lowtran7.cpython-310-darwin.so"
        if [ -f "$lowtran_native" ]; then
            if /usr/bin/xattr -p com.apple.quarantine "$lowtran_native" >/dev/null 2>&1 || ! /usr/bin/codesign --verify "$lowtran_native" >/dev/null 2>&1; then
                echo 'Checking bundled LOWTRAN7 trust metadata before importing it ...'
                "$PY" "$ROOT/scripts/repair_macos_lowtran.py" --repair || {
                    echo 'ERROR: project-local LOWTRAN7 signing failed; startup stopped.' >&2
                    exit 1
                }
            fi
        fi
    fi
    if preflight; then return; fi
    # In recent macOS builds, SciPy 1.15's wheel may have invalid Mach-O
    # zero-fill section offsets. Reinstalling the same wheel does not help.
    # Repair only SciPy .so files in this project's own venv, with backups.
    libraries_log="$( (cd "$BACKEND" && "$PY" "$ROOT/scripts/check_backend.py" --libraries-only) 2>&1 || true)"
    printf '%s\n' "$libraries_log"
    if [ "$(uname -s)" = 'Darwin' ]; then
        case "$libraries_log" in
            *"zero-fill section type"*)
                echo 'Detected a known SciPy Mach-O/dyld problem; repairing only this project .venv ...'
                "$PY" "$ROOT/scripts/repair_macos_scipy.py" --repair || {
                    echo 'ERROR: project-local SciPy binary repair failed; originals retained in .venv/.stratoq-native-backups/' >&2
                    exit 1
                }
                if preflight; then return; fi
                echo 'SciPy repair succeeded, but another scientific preflight check still fails; checking LOWTRAN signing ...' >&2
                ;;
        esac
    fi
    # A project archive moved between Macs may carry quarantine metadata or a
    # native LOWTRAN signature rejected by dyld. Only repair the exact bundled
    # CPython 3.10 extension, and only after the preflight reports its signature.
    if [ "$(uname -s)" = 'Darwin' ]; then
        full_preflight_log="$( (cd "$BACKEND" && "$PY" "$ROOT/scripts/check_backend.py") 2>&1 || true)"
        case "$full_preflight_log" in
            *"lowtran7.cpython-310-darwin.so"*"code signature"*|*"lowtran7.cpython-310-darwin.so"*"library load disallowed by system policy"*)
                echo 'macOS rejected the bundled LOWTRAN7 signature; repairing only that extension ...'
                "$PY" "$ROOT/scripts/repair_macos_lowtran.py" --repair || {
                    echo 'ERROR: LOWTRAN7 signature repair failed. The original binary was backed up.' >&2
                    exit 1
                }
                preflight || {
                    echo 'ERROR: LOWTRAN7 was re-signed, but the scientific preflight still fails.' >&2
                    exit 1
                }
                return
                ;;
        esac
    fi
    case "$libraries_log" in
        *"ModuleNotFoundError"*|*"No module named"*)
            echo 'Some Python dependencies are missing; installing requirements once ...'
            "$PY" -m pip install -r "$BACKEND/requirements.txt"
            preflight || { echo 'ERROR: preflight still fails. See the errors above.' >&2; exit 1; }
            return
            ;;
    esac
    echo 'ERROR: backend validation failed; packages will not be reinstalled in a loop.' >&2
    echo 'Run ./start-stratoq.sh --doctor to inspect the original error.' >&2
    exit 1
}
frontend_hash() { shasum -a 256 "$FRONTEND/package-lock.json" | awk '{print $1}'; }
setup_frontend() {
    command -v node >/dev/null 2>&1 || { echo 'ERROR: Node.js is missing (Vite 7 needs modern Node.js).' >&2; exit 1; }
    command -v npm >/dev/null 2>&1 || { echo 'ERROR: npm is missing.' >&2; exit 1; }
    desired="$(frontend_hash)"
    installed="$(cat "$FRONTEND/node_modules/.stratoq-lock-sha256" 2>/dev/null || true)"
    if [ ! -x "$FRONTEND/node_modules/.bin/vite" ] || [ "$installed" != "$desired" ]; then
        echo 'Installing frontend dependencies from package-lock.json ...'
        (cd "$FRONTEND" && npm ci)
        printf '%s\n' "$desired" > "$FRONTEND/node_modules/.stratoq-lock-sha256"
    fi
}
case "$MODE" in
    --doctor)
        if ! valid_venv; then echo "FAIL: backend/.venv is missing or invalid. Run ./start-stratoq.sh --setup" >&2; exit 1; fi
        preflight
        echo 'Frontend:'
        if [ -x "$FRONTEND/node_modules/.bin/vite" ]; then echo '  Vite installed'; else echo '  Vite missing; --setup installs it'; fi
        ;;
    --setup)
        setup_backend
        setup_frontend
        echo 'PASS: StratoQ dependencies and scientific environment are ready.'
        ;;
    --backend)
        setup_backend
        check_free_port 8000
        cd "$BACKEND"
        exec "$PY" -m uvicorn main:app --host 127.0.0.1 --port 8000
        ;;
    --frontend)
        setup_frontend
        cd "$FRONTEND"
        exec npm run dev -- --strictPort
        ;;
    --all)
        setup_backend
        setup_frontend
        check_free_port 8000
        check_free_port 5173
        (cd "$BACKEND" && exec "$PY" -m uvicorn main:app --host 127.0.0.1 --port 8000) &
        api_pid=$!
        cleanup() { kill "$api_pid" 2>/dev/null || true; wait "$api_pid" 2>/dev/null || true; }
        trap cleanup EXIT INT TERM
        echo 'Open http://127.0.0.1:5173/ (FastAPI: 127.0.0.1:8000)'
        cd "$FRONTEND"
        npm run dev -- --strictPort
        ;;
esac
