#!/bin/sh
set -eu

# Only operational logs; never touch tests, submissions, or database volumes.
for container in domserver judgehost-0 judgehost-1 judgehost-2 judgehost-3; do
  if docker ps --format '{{.Names}}' | grep -qx "$container"; then
    docker exec "$container" sh -lc '
      find /opt/domjudge /var/log -xdev -type f \( -name "*.log" -o -name "access.log" -o -name "error.log" \) -size +50M -exec truncate -s 0 {} \; 2>/dev/null || true
    ' || true
  fi
done

find /var/lib/docker/containers -name '*-json.log' -size +50M -exec truncate -s 0 {} \; 2>/dev/null || true
journalctl --vacuum-size=100M >/dev/null 2>&1 || true
apt-get clean >/dev/null 2>&1 || true
