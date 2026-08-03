#!/bin/sh
set -e

if [ "${RUN_WXDC_ON_START:-true}" = "true" ]; then
    python /app/wxdc.py

    if [ "${SMOKE_ONLY:-false}" = "true" ]; then
        exit 0
    fi
fi

mkdir -p /data/users /data/pending_orders /data/logs /data/keys

if [ -x /app/install_cron.sh ]; then
    /app/install_cron.sh
fi

exec python /app/server.py
