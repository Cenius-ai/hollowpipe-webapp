#!/usr/bin/env bash
# Hollowpipe demo - a non-interactive walk-through of one tide gate shift.
#
# Everything is written inside ./.demo-run, so your real ./hollowpipe_log.json
# is never touched. Runs unattended, needs no network, exits 0.
set -euo pipefail
cd "$(dirname "$0")"

ROOT="$(pwd)"
DEMO_DIR="$ROOT/.demo-run"
PYTHON="${PYTHON:-python3}"

rm -rf "$DEMO_DIR"
mkdir -p "$DEMO_DIR"
cd "$DEMO_DIR"

show_command() {
  printf '\n$ hollowpipe'
  local arg
  for arg in "$@"; do
    case "$arg" in
      *" "*) printf ' "%s"' "$arg" ;;
      *) printf ' %s' "$arg" ;;
    esac
  done
  printf '\n'
}

run() {
  show_command "$@"
  "$PYTHON" "$ROOT/hollowpipe.py" "$@"
}

run_fail() {
  show_command "$@"
  set +e
  "$PYTHON" "$ROOT/hollowpipe.py" "$@"
  local status=$?
  set -e
  printf '(exit %d)\n' "$status"
}

printf 'Hollowpipe demo - one tide gate shift, start to finish\n'
printf '======================================================\n'
printf 'python : %s\n' "$("$PYTHON" --version 2>&1)"
printf 'workdir: %s\n' "$DEMO_DIR"

printf '\n--- 0. version\n'
run --version

printf '\n--- 1. an empty log tells the keeper what to do next\n'
run list

printf '\n--- 2. log the tide gate operations of the shift\n'
run gate add --gate North --action closed --operator AB \
             --note "driftwood cleared from the sill"
sleep 1
run gate add --gate South --action open --operator AB \
             --note "spring tide, 3.1 m on the gauge"
sleep 1
run gate add --gate North --action open --operator RK \
             --note "handover to the night watch"

printf '\n--- 3. record the sluice angles set during the shift\n'
sleep 1
run sluice add --angle 42 --note "half gate, ebb running"
sleep 1
run sluice add --angle 0 --note "sluice shut for the flood"

printf '\n--- 4. take mud depth soundings above the sill\n'
sleep 1
run mud add --depth 12.5 --note "upstream sill, 40 cm rod"
sleep 1
run mud add --depth 34 --note "after the neap, settled"

printf '\n--- 5. read the whole shift back, newest first in each section\n'
run list

printf '\n--- 6. one record type only, and machine-readable output\n'
run list --type mud
run list --type gate --json

printf '\n--- 7. bad input is refused in one line and changes nothing\n'
run_fail gate add --action open
run_fail gate add --gate North --action ajar
run_fail sluice add --angle 130
run_fail sluice add --angle abc
run_fail mud add --depth -3
run_fail mud add --depth deep
printf 'entries still in the log: %s\n' \
  "$("$PYTHON" -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' hollowpipe_log.json)"

printf '\n--- 8. the log on disk is one plain JSON array\n'
printf 'file: %s\n' "$DEMO_DIR/hollowpipe_log.json"
printf 'size: %s bytes\n' "$(wc -c < hollowpipe_log.json)"

printf '\n--- 9. --help is the full manual\n'
"$PYTHON" "$ROOT/hollowpipe.py" --help

printf '\nDemo complete. The demo log lives at %s\n' "$DEMO_DIR/hollowpipe_log.json"
printf 'Your own %s/hollowpipe_log.json was not touched.\n' "$ROOT"
