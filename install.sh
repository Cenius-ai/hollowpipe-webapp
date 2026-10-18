#!/usr/bin/env bash
# Hollowpipe setup: project-level dependencies only, then exit.
# Safe to re-run. Never starts a server and never touches your shift log.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "error: $PYTHON not found - install Python 3.9 or newer (see INSTALL.md)" >&2
  exit 1
fi

echo "==> upgrading pip, setuptools and wheel"
"$PYTHON" -m pip install --upgrade --quiet pip setuptools wheel

echo "==> installing test dependencies from requirements.txt"
"$PYTHON" -m pip install --quiet -r requirements.txt

echo "==> installing the 'hollowpipe' console script (editable, no build isolation)"
"$PYTHON" -m pip install --quiet --no-build-isolation -e .

echo "==> self-check"
"$PYTHON" -c "import hollowpipe; print('hollowpipe', hollowpipe.__version__, 'imports cleanly')"
"$PYTHON" hollowpipe.py --version

cat <<'DONE'

Setup complete. There is nothing to migrate or seed: the log is a single JSON
array at ./hollowpipe_log.json in whatever directory you run the tool from,
and it is created on the first entry you log.

  python3 hollowpipe.py --help
  python3 hollowpipe.py list
  bash demo.sh                      # seeded walk-through in ./.demo-run
  python3 -m pytest                 # the test suite
DONE
