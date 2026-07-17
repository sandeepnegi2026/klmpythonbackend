"""Harvest product spellings off the WARM extract cache (no re-extraction) and write
them in build_product_synonyms' cache format, so `--apply --from-cache` can fold any
NEW ones into both product_master.json mirrors instantly.

Usage:  _warm_harvest.py <batch_name|--folder PATH> <out_cache.json>
"""
import sys, json
sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import batch_extract as be
import batch_core as bc
import run_batch
from pathlib import Path

mode = sys.argv[1]
out = sys.argv[2]
if mode == "--folder":
    jobs = list(run_batch.discover_folder(Path(sys.argv[3])))
    out = sys.argv[4]
else:
    jobs = list(run_batch.iter_batch(mode, Path("batches.json")))

spellings, miss = {}, 0
for route, path in jobs:
    res = be.get(route, str(path))
    if not isinstance(res, dict) or res.get("_extract_error"):
        miss += 1
        continue
    div = run_batch._division_hint(path)
    for name in bc.harvest_spellings(res):
        spellings.setdefault(name, div)

json.dump({"spellings": spellings, "failures": []},
          open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"jobs={len(jobs)}  cache_miss={miss}  distinct_spellings={len(spellings)}  -> {out}")
