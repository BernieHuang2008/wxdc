#!/bin/sh
set -e

CRON_SCHEDULE="${CRON_SCHEDULE:-0 16 * * 5}"
CRON_LOG_FILE="${CRON_LOG_FILE:-/data/logs/wxdc-cron.log}"

mkdir -p /data/logs
printf '%s\n' "${CRON_SCHEDULE} cd /app && /usr/local/bin/python /app/wxdc.py >> ${CRON_LOG_FILE} 2>&1" > /etc/cron.d/wxdc
chmod 0644 /etc/cron.d/wxdc
