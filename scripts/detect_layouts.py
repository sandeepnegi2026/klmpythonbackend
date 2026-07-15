#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from extractors import party_pdf, party_xlsx, stock_pdf, stock_xlsx

root = Path(ROOT / ".." / "..").resolve()
reports = Path(ROOT / "..").resolve()

folders = [
    ("party_xlsx", reports / "Party Wise/Partty-diff", [".xlsx", ".xls", ".XLS", ".XLSX"]),
    ("party_pp_xlsx", reports / "New/PP/PP", [".xlsx", ".xls", ".XLS", ".XLSX"]),
    ("stock_pdf", reports / "Sales Reports Wise/Sales Diff", [".pdf", ".PDF", ".Pdf"]),
    ("stock_xlsx", reports / "Sales Reports Wise/Sales Diff", [".xlsx", ".xls", ".XLS", ".XLSX"]),
]

for route, folder, exts in folders:
    if not folder.exists():
        print(f"SKIP {route}: {folder}")
        continue
    print(f"=== {route} ===")
    for path in sorted(folder.iterdir()):
        if path.suffix not in exts:
            continue
        data = path.read_bytes()
        if route.startswith("party"):
            result = party_xlsx.extract(data, {"filename": path.name})
            layout = result.get("debug", {}).get("layout")
        elif route == "stock_pdf":
            result = stock_pdf.extract(data, {})
            layout = result.get("debug", {}).get("layout")
        else:
            result = stock_xlsx.extract(data, {"filename": path.name})
            layout = result.get("debug", {}).get("layout")
        print(f"  {path.name}: {layout}")
