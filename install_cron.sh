#!/bin/sh
set -e

CRON_SCHEDULE_CURRENT="${CRON_SCHEDULE_CURRENT:-${CRON_SCHEDULE:-0 16 * * 5}}"
CRON_SCHEDULE_NEXT="${CRON_SCHEDULE_NEXT:-0 12 * * 0}"
CRON_LOG_FILE="${CRON_LOG_FILE:-/data/logs/wxdc.log}"

mkdir -p /data/logs
printf '%s\n' \
    "SHELL=/bin/sh" \
    "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    "TZ=${TZ:-Asia/Shanghai}" \
    "DATA_DIR=${DATA_DIR:-/data}" \
    "CONFIG_PATH=${CONFIG_PATH:-/data/config.yaml}" \
    "${CRON_SCHEDULE_CURRENT} root cd /app && /usr/local/bin/python /app/wxdc.py --runschedule --week current > ${CRON_LOG_FILE} 2>&1 && echo \$(date) >> /data/logs/cron_activation.log" \
    "${CRON_SCHEDULE_NEXT} root cd /app && /usr/local/bin/python /app/wxdc.py --runschedule --week next > ${CRON_LOG_FILE} 2>&1 && echo \$(date) >> /data/logs/cron_activation.log" > /etc/cron.d/wxdc
chmod 0644 /etc/cron.d/wxdc
