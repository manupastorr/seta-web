#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

if [[ ! -x "$PY" ]]; then
  echo "Creating Python venv..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$ROOT/requirements.txt"
fi

cd "$ROOT"
SCAN_ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "--quick" ]]; then
    SCAN_ARGS+=(--skip-edges)
  else
    SCAN_ARGS+=("$arg")
  fi
done
echo "Scanning library (cached analysis reused when possible)..."
if [[ ${#SCAN_ARGS[@]} -gt 0 && " ${SCAN_ARGS[*]} " == *" --skip-edges "* ]]; then
  echo "Quick scan: skipping mix-edge rebuild"
fi
if [[ ${#SCAN_ARGS[@]} -gt 0 ]]; then
  "$PY" scan_library.py "${SCAN_ARGS[@]}"
else
  "$PY" scan_library.py
fi

echo "Starting Seta..."
exec "$PY" server.py
