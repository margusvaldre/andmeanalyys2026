#!/bin/sh
set -eu

mkdir -p /var/log/praktikum
touch /var/log/praktikum/pipeline.log

ln -snf "/usr/share/zoneinfo/${TZ:-Europe/Tallinn}" /etc/localtime
echo "${TZ:-Europe/Tallinn}" > /etc/timezone

sed 's/\r$//' /app/scheduler/crontab | crontab -

echo "[scheduler] Cron käivitus $(date --iso-8601=seconds)" >> /var/log/praktikum/pipeline.log

if [ "${RUN_ON_STARTUP:-false}" = "true" ]; then
    echo "[scheduler] Stardil käivitan run-all $(date --iso-8601=seconds)" >> /var/log/praktikum/pipeline.log
    cd /app
    /usr/local/bin/python /app/scripts/run_pipeline.py run-all >> /var/log/praktikum/pipeline.log 2>&1 || {
        echo "[scheduler] Stardil run-all ebaõnnestus $(date --iso-8601=seconds)" >> /var/log/praktikum/pipeline.log
    }
fi

exec cron -f
