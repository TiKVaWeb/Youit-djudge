#!/bin/sh
set -eu

# Run after 50-domjudge.sh has generated the base URL/proxy configuration.
config=/etc/nginx/snippets/domjudge-inner
include='include /etc/nginx/snippets/domjudge-event-feed;'
if ! grep -Fqx "$include" "$config"; then
    printf '\n%s\n' "$include" >> "$config"
fi
