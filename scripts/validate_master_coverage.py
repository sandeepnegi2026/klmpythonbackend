import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from extractors.party_pdf.pipeline import extract as extract_party_pdf
from extractors.party_xlsx.pipeline import extract as extract_party_xlsx
from extractors.stock_pdf.pipeline import extract as extract_stock_pdf
from extractors.stock_xlsx.pipeline import extract as extract_stock_xlsx

def main():
    manifest_path = os.path.join(os.path.dirname(__file__), "..", "tests", "regression_manifest.json")
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
    reports_root = r"D:\Devs\Reports\Data"
    
    total_rows = 0
    matched_rows = 0
    unmatched_names = set()
    
    import importlib.util
    spec = importlib.util.spec_from_file_location("regression_test", os.path.join(os.path.dirname(__file__), "regression_test.py"))
    reg_test = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reg_test)
    
    print(f"Loaded {len(manifest.get('suites', {}))} suites")
    for suite_name, suite_info in manifest.get("suites", {}).items():
        extractor_type = suite_info.get("route")
        
        files = reg_test._resolve_glob(Path(reports_root), suite_info.get("glob", ""))
        
        print(f"Suite {suite_name}: {len(files)} files")
        
        for file_path in files:
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                continue
                
            with open(file_path, "rb") as f:
                data = f.read()
                
            if extractor_type == "party_pdf":
                res = extract_party_pdf(data)
            elif extractor_type == "party_xlsx":
                res = extract_party_xlsx(data)
            elif extractor_type == "stock_pdf":
                res = extract_stock_pdf(data)
            elif extractor_type == "stock_xlsx":
                res = extract_stock_xlsx(data)
            else:
                continue
                
            for row in res.get("rows", []):
                if "product_name" not in row:
                    continue
                
                total_rows += 1
                if "raw_product_name" in row:
                    matched_rows += 1
                else:
                    unmatched_names.add(row["product_name"])
                    
    print("=== Master Product Validation Report ===")
    print(f"Total product rows extracted: {total_rows}")
    print(f"Rows matched to master.json:  {matched_rows}")
    if total_rows > 0:
        print(f"Match Rate:                   {(matched_rows/total_rows)*100:.1f}%")
        
    if unmatched_names:
        print(f"\nFound {len(unmatched_names)} unique products NOT in master JSON:")
        for name in sorted(list(unmatched_names))[:20]:
            print(f" - {name}")
        if len(unmatched_names) > 20:
            print(f"   ... and {len(unmatched_names) - 20} more.")

if __name__ == "__main__":
    main()
