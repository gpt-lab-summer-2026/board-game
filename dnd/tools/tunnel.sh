#!/usr/bin/env bash
# Keep the SSH tunnel to the cluster's model gateway up.
#
# The gateway lives on gpu-farmi-004:9000 but the firewall between the Pi and
# the cluster only lets :11434 through, so port 9000 is reached over SSH. A
# plain `ssh -N -L` dies with the shell that started it, and when it does the
# demo goes silent -- the voice loop and autoplay both fall back from ~2s
# cluster Kokoro to ~10s local, or to nothing at all. That silence looks like a
# bug in the audio code and is not one.
#
# This runs the tunnel in a restart loop, detached, so a dropped connection
# comes back on its own.
#
#   tools/tunnel.sh start | stop | status
set -uo pipefail

HOST="${CLUSTER_HOST:-sampo@gpu-farmi-004.rd.tuni.fi}"
KEY="${CLUSTER_KEY:-$HOME/.ssh/raspi_key}"
PORT="${GATEWAY_PORT:-9000}"
LOG="${TUNNEL_LOG:-/tmp/gateway-tunnel.log}"
TAG="dnd-gateway-tunnel"

listening() { ss -ltn 2>/dev/null | grep -q ":${PORT}[[:space:]]"; }
loop_pids() { pgrep -f "$TAG" 2>/dev/null | grep -v "^$$\$"; }

start() {
    if listening; then echo "tunnel: already listening on :${PORT}"; return 0; fi
    if [ ! -f "$KEY" ]; then echo "tunnel: no key at $KEY"; return 1; fi

    # The marker in the command line is what stop/status find it by.
    setsid nohup bash -c "
        export ${TAG}=1
        while true; do
            ssh -N -T \
                -o ExitOnForwardFailure=yes \
                -o ServerAliveInterval=20 -o ServerAliveCountMax=3 \
                -o StrictHostKeyChecking=accept-new \
                -o BatchMode=yes \
                -L ${PORT}:localhost:${PORT} -i '${KEY}' '${HOST}' \
                >> '${LOG}' 2>&1
            echo \"[\$(date -Is)] ${TAG}: link dropped, retrying in 5s\" >> '${LOG}'
            sleep 5
        done
    " >> "$LOG" 2>&1 < /dev/null &
    disown -a 2>/dev/null || true

    for _ in $(seq 1 30); do
        sleep 1
        listening && { echo "tunnel: up, :${PORT} forwarded to ${HOST}"; return 0; }
    done
    echo "tunnel: did NOT come up within 30s -- see $LOG"
    tail -10 "$LOG"
    return 1
}

stop() {
    local p; p="$(loop_pids)" || true
    [ -n "$p" ] && kill $p 2>/dev/null
    pkill -f "ssh -N -T .*-L ${PORT}:localhost:${PORT}" 2>/dev/null
    sleep 1
    listening && echo "tunnel: still listening (someone else's?)" || echo "tunnel: stopped"
}

case "${1:-status}" in
    start) start ;;
    stop) stop ;;
    status)
        listening && echo "tunnel: listening on :${PORT}" || echo "tunnel: DOWN"
        curl -s -m 4 -o /dev/null "http://127.0.0.1:${PORT}/models" \
            && echo "gateway: answering" || echo "gateway: not answering"
        ;;
    *) echo "usage: $0 {start|stop|status}"; exit 2 ;;
esac
