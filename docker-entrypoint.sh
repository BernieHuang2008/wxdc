#!/bin/sh
set -e

mkdir -p /data/users /data/pending_orders /data/logs /data/keys

if [ -x /app/install_cron.sh ]; then
    /app/install_cron.sh
fi

exec python /app/server.py
