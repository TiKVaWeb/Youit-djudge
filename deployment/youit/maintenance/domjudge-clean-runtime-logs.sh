#!/bin/sh
set -eu

# Reporting only: truncating Docker's JSON files bypasses log rotation and
# destroys diagnostics needed to investigate stalled submissions.
for arg in "$@"; do
  case "$arg" in
    --dry-run) ;;
    *) echo 'Only --dry-run is supported; use Docker-managed log rotation.' >&2; exit 2 ;;
  esac
done
for container in domserver judgehost-0 judgehost-1 judgehost-2 judgehost-3; do
  if docker ps --format '{{.Names}}' | grep -qx "$container"; then
    echo "container=$container oversized_logs:"
    docker exec "$container" sh -c '
      find /opt/domjudge /var/log -xdev -maxdepth 4 -type f \
        -name "*.log" -size +50M -printf "%s %p\n" 2>/dev/null
    '
  fi
done
journalctl --disk-usage
echo 'report_only=true deleted_logs=0'
