#!/bin/sh
set -eu
LOCK=/run/domjudge-clean-judgehost-workdirs.lock
ROOT=/mnt/domjudge-judgehost/judgings
AGE_MINUTES=${AGE_MINUTES:-360}
LOG_TAG=domjudge-clean-judgehost-workdirs
(
  flock -n 9 || exit 0
  [ -d "$ROOT" ] || exit 0
  before=$(df -ih "$ROOT" | awk "NR==2 {print \$5 \" used, \" \$4 \" free\"}")
  deleted=0
  for base in "$ROOT"/judgedaemon-*/endpoint-default; do
    [ -d "$base" ] || continue
    count=$(find "$base" -xdev -mindepth 1 -maxdepth 1 -type d -regextype posix-extended -regex ".*/[0-9]+" -mmin +"$AGE_MINUTES" -print | wc -l)
    if [ "$count" -gt 0 ]; then
      find "$base" -xdev -mindepth 1 -maxdepth 1 -type d -regextype posix-extended -regex ".*/[0-9]+" -mmin +"$AGE_MINUTES" -exec rm -rf -- {} +
      deleted=$((deleted + count))
    fi
  done
  after=$(df -ih "$ROOT" | awk "NR==2 {print \$5 \" used, \" \$4 \" free\"}")
  logger -t "$LOG_TAG" "deleted_dirs=$deleted age_minutes=$AGE_MINUTES before=[$before] after=[$after]"
) 9>"$LOCK"
