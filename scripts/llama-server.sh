#!/usr/bin/env bash
# Canonical launcher for the local gemma3 server that src/llm/ talks to.
#
# --swa-full is a latency fix, not a tuning knob. gemma3 is a sliding-window
# attention model (sliding_window=1024). In this llama.cpp build, when the
# prompt is much shorter than that window, the SWA checkpoint path rejects its
# own checkpoint and forces n_past=0 -- throwing away the common prefix it just
# computed correctly, so the full ~15s prefill is repaid on every single call.
# --swa-full disables that path; the full-size SWA cache it costs is negligible
# at -c 4096.
#
# --no-slots because /slots is ENABLED by default in this build and would
# expose prompt text to anything that can reach the port.
set -euo pipefail

cd "$(dirname "$0")/.."

exec llama-server \
  -m models/gemma-3-4b-it-q4_k_m.gguf \
  --host 127.0.0.1 --port 8091 \
  -c 4096 -t 4 -tb 4 -np 1 \
  --swa-full \
  --no-webui \
  --no-slots \
  -fa auto \
  "$@"
