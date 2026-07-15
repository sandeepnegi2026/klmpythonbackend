#!/usr/bin/env bash
# Block until all 3 remaining harvest caches are written, then exit so the agent resumes.
need="_hb_party.json _hb_sales.json _hb_guj.json"
deadline=$(( $(date +%s) + 3600 ))   # 60-min safety cap
while :; do
  miss=""
  for f in $need; do [ -s "$f" ] || miss="$miss $f"; done
  if [ -z "$miss" ]; then echo "ALL CACHES READY"; for f in _hb_*.json; do echo " $f $(stat -c%s "$f")B"; done; exit 0; fi
  [ "$(date +%s)" -ge "$deadline" ] && { echo "TIMEOUT still missing:$miss"; exit 2; }
  sleep 30
done
