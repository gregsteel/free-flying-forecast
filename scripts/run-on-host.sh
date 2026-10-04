#!/bin/bash
# Host wrapper for launchd: make sure Colima is running with the agreed VM size, then run the
# pipeline in the container. Settings come from ~/.config/ffforecast/env (see README).
set -euo pipefail

CONF="${FFFORECAST_ENV:-$HOME/.config/ffforecast/env}"
[ -f "$CONF" ] && . "$CONF"

DATA="${FFFORECAST_DATA:-$HOME/ffforecast-data}"
MODEL="${FFFORECAST_MODEL:-gfs}"
IMAGE="${FFFORECAST_IMAGE:-ffforecast}"
mkdir -p "$DATA"/{cache,state,out,work}

# Constitution III: at most 8 CPUs and 10 GB for the VM.
if ! colima status >/dev/null 2>&1; then
  colima start --cpu 8 --memory 10 --disk 80 --vm-type vz
fi

# `run-on-host.sh poll` checks AUSRASP and rebuilds if its data changed (specs/003); the default is a full run.
if [ "${1:-}" = "poll" ]; then
  ARGS=(poll --if-due)
else
  ARGS=(run --model "$MODEL")
fi
KEYMOUNT=()
if [ -n "${FFFORECAST_PUBLISH_REMOTE:-}" ]; then
  ARGS+=(--publish-remote "$FFFORECAST_PUBLISH_REMOTE")
  if [ -n "${FFFORECAST_DEPLOY_KEY:-}" ]; then
    KEYMOUNT=(-v "$FFFORECAST_DEPLOY_KEY:/run/deploy_key:ro")
    ARGS+=(--publish-key /run/deploy_key)
  fi
fi

exec docker run --rm \
  -v "$DATA/cache:/app/cache" -v "$DATA/state:/app/state" \
  -v "$DATA/out:/app/out" -v "$DATA/work:/app/work" \
  ${KEYMOUNT[@]+"${KEYMOUNT[@]}"} \
  "$IMAGE" "${ARGS[@]}"
