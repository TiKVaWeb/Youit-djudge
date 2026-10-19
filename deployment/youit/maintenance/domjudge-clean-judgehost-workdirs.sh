#!/bin/sh
set -eu
# Both cleaners use the same lock; no host restarts are needed for finished workdirs.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$script_dir/domjudge_workdir_cleanup.py" --age-minutes "${AGE_MINUTES:-360}" "$@"
