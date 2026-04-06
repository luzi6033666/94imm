#!/bin/bash

set -eu

BASE_DIR="/opt/mm187"
CRAWLER_DIR="${BASE_DIR}/crawler"
PYTHON_BIN="${BASE_DIR}/.venv/bin/python"
# Gray defaults: prefer the sources that are currently stable and reachable
# from the gray host. Keep 06se available in the repo, but do not make it
# part of the default live rotation while its upstream image CDN is flaky.
CRAWLER_SCRIPTS="${CRAWLER_SCRIPTS:-crawler_meirentu.py crawler_huotumao.py crawler_coserlab.py crawler_miaoyinshe.py crawler_miaohuaying.py crawler_xiaomiaoshe.py}"
HEALTH_SCRIPT="source_health.py"

cd "${CRAWLER_DIR}"

while true; do
    if [ -f "${HEALTH_SCRIPT}" ]; then
        echo "[$(date '+%F %T')] source health"
        "${PYTHON_BIN}" -u "${HEALTH_SCRIPT}" || true
    fi

    for crawler_script in ${CRAWLER_SCRIPTS}; do
        echo "[$(date '+%F %T')] start ${crawler_script}"
        if ! timeout 20m "${PYTHON_BIN}" -u "${crawler_script}"; then
            echo "[$(date '+%F %T')] failed ${crawler_script}" >&2
        fi
    done

    sec=$(shuf -i 7200-21600 -n 1)
    date
    echo "sleep ${sec} s"
    echo ""
    echo ""
    echo ""
    echo ""
    sleep "${sec}"
done
