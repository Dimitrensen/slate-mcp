#!/bin/sh
# Root only to make the volume private, then the server runs as uid 1000.
set -eu

if ! mkdir -p /data || ! chown slate:slate /data || ! chmod 700 /data; then
    echo "Slate needs a writable /data volume for its SQLite database." >&2
    exit 1
fi

exec setpriv \
    --reuid=slate \
    --regid=slate \
    --init-groups \
    --inh-caps=-all \
    -- slate "$@"
