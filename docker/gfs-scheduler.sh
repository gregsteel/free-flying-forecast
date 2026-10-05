#!/bin/bash
# Long-running loop for the container: a forecast run at each time in FFFORECAST_RUN_TIMES (local
# time, TZ is Australia/Melbourne), `poll --if-due` every tick, and `observe --if-due` (the station's
# measured wind, daily: the time is [observations] run_time in the site config). Publishing is on when
# FFFORECAST_PUBLISH_REMOTE is set; FFFORECAST_DEPLOY_KEY is the path of a mounted SSH deploy key.
set -u

RUN_TIMES="${FFFORECAST_RUN_TIMES:-05:30 15:30}"
TICK_S="${FFFORECAST_TICK_S:-300}"
MARKERS=/app/state/scheduled
mkdir -p "$MARKERS"

ARGS=()
if [ -n "${FFFORECAST_PUBLISH_REMOTE:-}" ]; then
  ARGS+=(--publish-remote "$FFFORECAST_PUBLISH_REMOTE")
  if [ -n "${FFFORECAST_DEPLOY_KEY:-}" ]; then
    if [ ! -f "$FFFORECAST_DEPLOY_KEY" ]; then
      # Docker makes a missing bind-mount source on the host an empty directory.
      echo "scheduler: $FFFORECAST_DEPLOY_KEY is not a file; the key must exist on the host before the stack starts" >&2
      exit 1
    fi
    # ssh refuses a key that others can read, and mounted files often are.
    install -m 600 "$FFFORECAST_DEPLOY_KEY" /tmp/deploy_key
    ARGS+=(--publish-key /tmp/deploy_key)
  fi
fi

ffforecast check || exit 1
echo "scheduler: runs at ${RUN_TIMES} ${TZ:-UTC}, polling every ${TICK_S}s (when due)"
first=1
while true; do
  today="$(date +%F)"
  now="$(date +%H:%M)"
  # keep only today's markers
  find "$MARKERS" -type f ! -name "$today-*" -delete
  due=0
  [ "$first" = 1 ] && due=1  # a run on start-up; an already-published cycle is skipped
  for t in $RUN_TIMES; do
    marker="$MARKERS/$today-${t/:/}"
    if [[ ! "$now" < "$t" ]] && [ ! -e "$marker" ]; then
      touch "$marker"
      due=1
    fi
  done
  # the station's measured wind: once a day after the flying, or at once after a missed day
  ffforecast observe --if-due || echo "scheduler: observe failed ($?)"
  if [ "$due" = 1 ]; then
    ffforecast run --model "${FFFORECAST_MODEL:-gfs}" ${ARGS[@]+"${ARGS[@]}"} || echo "scheduler: run failed ($?)"
  else
    ffforecast poll --if-due ${ARGS[@]+"${ARGS[@]}"} || echo "scheduler: poll failed ($?)"
  fi
  first=0
  sleep "$TICK_S"
done
