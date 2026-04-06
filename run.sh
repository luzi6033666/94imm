#!/bin/sh

set -eu

SERVICE_NAME="mm187"

run_start() {
    systemctl start "${SERVICE_NAME}"
}

run_stop() {
    systemctl stop "${SERVICE_NAME}"
}

run_restart() {
    systemctl restart "${SERVICE_NAME}"
}

run_status() {
    systemctl --no-pager --full status "${SERVICE_NAME}"
}

run_clear() {
    find cache -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
}

case "${1:-}" in
    "start"|"s"|"S")
        run_start
        echo "website run successfully"
        ;;
    "restart"|"r"|"R")
        run_clear
        run_restart
        echo "website restart successfully"
        ;;
    "clear"|"c"|"C")
        run_clear
        echo "cache cleared"
        ;;
    "stop")
        run_stop
        echo "website closed"
        ;;
    "status")
        run_status
        ;;
    *)
        echo "Use command to:"
        echo "-s       start website"
        echo "-r       restart website"
        echo "-c       clear cache"
        echo "-stop    stop website"
        echo "-status  show service status"
        ;;
esac
