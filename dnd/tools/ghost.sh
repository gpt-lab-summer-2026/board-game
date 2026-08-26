#!/usr/bin/env bash
# Start, stop and restart the ghost as one atomic operation.
#
# Restarting it by hand from an interactive shell is how the board ends up with
# no ghost at all: the kill lands, the shell dies before the relaunch, and the
# console spends the rest of the session refusing connections with errno 111.
# Doing both halves inside one detached script means a parent that goes away
# cannot leave the ghost half-restarted.
#
#   tools/ghost.sh start | stop | restart | status | log
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PA="$ROOT/PlanarAlly"
PY="$PA/server/.venv/bin/python"
LOG="${GHOST_LOG:-/tmp/ghost.log}"
PATTERN='[p]ython -m ghost'

pids() { pgrep -f "$PATTERN" 2>/dev/null; }

stop() {
    local p
    p="$(pids)" || true
    if [ -z "$p" ]; then echo "ghost: already stopped"; return 0; fi
    echo "ghost: stopping $p"
    kill $p 2>/dev/null
    for _ in $(seq 1 20); do
        sleep 0.5
        [ -z "$(pids)" ] && { echo "ghost: stopped"; return 0; }
    done
    echo "ghost: still up, sending KILL"
    kill -9 $(pids) 2>/dev/null
    sleep 1
}

start() {
    if [ -n "$(pids)" ]; then echo "ghost: already running: $(pids)"; return 0; fi
    cd "$PA" || { echo "ghost: no $PA"; return 1; }
    XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" \
        setsid nohup "$PY" -m ghost --host 0.0.0.0 >> "$LOG" 2>&1 < /dev/null &
    disown -a 2>/dev/null || true
    # The console binds before Kokoro finishes loading, but give it room.
    for _ in $(seq 1 60); do
        sleep 1
        if curl -s -m 2 http://127.0.0.1:8770/state >/dev/null 2>&1; then
            echo "ghost: up as $(pids), console answering"
            return 0
        fi
    done
    echo "ghost: did NOT come up within 60s -- see $LOG"
    tail -20 "$LOG"
    return 1
}

status() {
    local p; p="$(pids)" || true
    if [ -z "$p" ]; then echo "ghost: stopped"; else echo "ghost: running as $p"; fi
    if curl -s -m 2 http://127.0.0.1:8770/state >/dev/null 2>&1; then
        echo "console: answering on :8770"
    else
        echo "console: NOT answering on :8770"
    fi
}

case "${1:-status}" in
    start)   start ;;
    stop)    stop ;;
    restart) stop; start ;;
    status)  status ;;
    log)     grep -vE "aiohttp.access" "$LOG" | tail -"${2:-30}" ;;
    *)       echo "usage: $0 {start|stop|restart|status|log}"; exit 2 ;;
esac
