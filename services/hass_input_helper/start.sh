#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_PATH" ]; then
  python3 -m venv "$VENV_PATH"
fi

# shellcheck disable=SC1090
source "$VENV_PATH/bin/activate"

pip install --upgrade pip >/dev/null
pip install -r "$SCRIPT_DIR/requirements.txt"

FRONTEND_DIR="$SCRIPT_DIR/frontend"
if [ -d "$FRONTEND_DIR" ]; then
  mkdir -p "$SCRIPT_DIR/static"
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm is required to build the frontend assets." >&2
    exit 1
  fi
  pushd "$FRONTEND_DIR" >/dev/null
  if [ -f package-lock.json ]; then
    npm ci
  else
    npm install
  fi
  npm run build
  popd >/dev/null
fi

REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

exec uvicorn services.hass_input_helper.app:app --host 0.0.0.0 --port 8100 --reload
