#!/bin/sh
set -e

CRON_SCHEDULE="${CRON_SCHEDULE:-0 16 * * 5}"
CRON_LOG_FILE="${CRON_LOG_FILE:-/data/logs/wxdc.log}"

mkdir -p /data/logs
printf '%s\n' \
    "SHELL=/bin/sh" \
    "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    "TZ=${TZ:-Asia/Shanghai}" \
    "DATA_DIR=${DATA_DIR:-/data}" \
    "CONFIG_PATH=${CONFIG_PATH:-/data/config.yaml}" \
    "${CRON_SCHEDULE} root cd /app && /usr/local/bin/python /app/wxdc.py --runschedule > ${CRON_LOG_FILE} 2>&1 && echo $(date) >> /data/logs/cron_activation.log" > /etc/cron.d/wxdc
chmod 0644 /etc/cron.d/wxdc
