#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "${1:-}" = '--doctor' ]; then exec "$ROOT/start-stratoq.sh" --doctor; fi
if [ "${1:-}" = '--setup' ]; then exec "$ROOT/start-stratoq.sh" --setup; fi
exec "$ROOT/start-stratoq.sh" --backend
