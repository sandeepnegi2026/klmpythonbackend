#!/usr/bin/env bash
deadline=$(( $(date +%s) + 5400 ))   # 90-min cap
while :; do
  if [ -s _hb_guj.json ]; then echo "GUJ READY $(stat -c%s _hb_guj.json)B"; exit 0; fi
  # also exit if the worker died without writing (avoid waiting forever on a crash)
  if ! tasklist 2>/dev/null | grep -qi python; then echo "NO PYTHON ALIVE and no guj cache"; exit 3; fi
  [ "$(date +%s)" -ge "$deadline" ] && { echo "TIMEOUT"; exit 2; }
  sleep 30
done
