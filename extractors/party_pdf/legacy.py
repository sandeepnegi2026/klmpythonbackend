import io
import time

import pandas as pd

from extractors.party_pdf.legacy_fields import match_field


def extract_excel(file_bytes, file_name):
    started = time.perf_counter()
    result = {
        "pages": [],
        "file_size_bytes": len(file_bytes),
        "source": "excel",
        "total_pages": 0,
        "detected_format": "excel",
        "format_label": "Excel",
        "auto_report_type": "Party-wise Sales",
    }
    try:
        engine = "xlrd" if file_name.lower().endswith(".xls") else "openpyxl"
        xls = pd.ExcelFile(io.BytesIO(file_bytes), engine=engine)
        result["total_pages"] = len(xls.sheet_names)
        all_rows = []
        headers = None
        for sheet in xls.sheet_names:
            df = xls.parse(sheet, header=None)
            if df.empty:
                continue
            for idx in range(min(10, len(df))):
                rv = [
                    str(v).strip()
                    for v in df.iloc[idx]
                    if pd.notna(v) and str(v).strip()
                ]
                if sum(1 for v in rv if match_field(v)[0] is not None) >= 3:
                    headers = [
                        str(v).strip() if pd.notna(v) else f"col_{i}"
                        for i, v in enumerate(df.iloc[idx])
                    ]
                    for _, row in df.iloc[idx + 1 :].iterrows():
                        vals = [str(v).strip() if pd.notna(v) else "" for v in row]
                        if any(v for v in vals):
                            all_rows.append(vals[: len(headers)])
                    break
            if headers:
                break
            if not headers:
                headers = [
                    str(v).strip() if pd.notna(v) else f"col_{i}"
                    for i, v in enumerate(df.iloc[0])
                ]
                for _, row in df.iloc[1:].iterrows():
                    vals = [str(v).strip() if pd.notna(v) else "" for v in row]
                    if any(v for v in vals):
                        all_rows.append(vals[: len(headers)])
            result["pages"].append(
                {
                    "page_number": 1,
                    "text": df.to_string()[:2000],
                    "width": 0,
                    "height": 0,
                    "char_count": 0,
                    "line_count": 0,
                    "rect_count": 0,
                }
            )
        result["parsed_headers"] = headers or []
        result["parsed_rows"] = all_rows
    except Exception as e:
        result["parse_error"] = str(e)
        result["parsed_headers"] = []
        result["parsed_rows"] = []
    result["runtime_ms"] = int((time.perf_counter() - started) * 1000)
    return result


def result_to_dataframe(result):
    if result.get("parsed_rows"):
        h = result["parsed_headers"]
        rows = result["parsed_rows"]
        mx = len(h)
        padded = [r + [""] * (mx - len(r)) if len(r) < mx else r[:mx] for r in rows]
        return pd.DataFrame(padded, columns=h)
    return pd.DataFrame()


def build_xlsx(df):
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def build_csv(df):
    return df.to_csv(index=False).encode("utf-8")
