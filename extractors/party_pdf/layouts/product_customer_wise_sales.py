import io
import re

# Column x-boundaries observed in the SwilERP "Product-Customer Wise Sales"
# fixed-column layout (CAPITAL PHARMA AGENCIES):
#   Customer  x0  7..~200      Station  x0 ~343..    Qty  right ~668    Value right ~792
# The name<->station split is genuinely ambiguous in the flat text
# (e.g. "SEN BROTHERS P.S.-HARE STREE", "LIFE LINE JADAVPUR MEHTA BUILDING"),
# so this parser reads word x-coordinates to slice the columns positionally.
_STATION_X = 330   # station column starts ~343
_QTY_X = 600       # qty column ~654-668
_VAL_X = 720       # value column ~751-792

_VAL_RE = re.compile(r"^-?\d[\d,]*\.\d{1,2}$")
_QTY_RE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")
# a product-code leading token: letters immediately followed by a dot or digit
# (KLM2.11, KLM119, KLM.11, KLM9004) — distinguishes a PRODUCT band from a
# DIVISION band (bare "KLM PEDIA", "KLM COSMOCOR").
_CODE_RE = re.compile(r"^[A-Za-z]{1,6}[.\d][\w.\-/]*$")
_PACKISH = re.compile(r"\d")


def _is_furniture(joined):
    low = joined.lower()
    if not joined:
        return True
    if low.startswith("page no") or "continued" in low or "powered by" in low:
        return True
    if low.startswith("customer station") or low.startswith("customer  station"):
        return True
    if "capital pharma" in low or "b.r.b.basu" in low or "product-customer wise" in low:
        return True
    if joined.startswith("TOTAL") or joined.startswith("GRAND TOTAL"):
        return True
    # separators / band terminators made only of dashes / asterisks
    if re.fullmatch(r"[-*\s]+", joined):
        return True
    return False


def _num(t):
    return t.replace(",", "")


def parse_product_customer_wise_sales(text, file_bytes=None):
    """SwilERP 'Product-Customer Wise Sales' (CAPITAL PHARMA AGENCIES).

    Nesting:  DIVISION band ("KLM PEDIA")  ->  PRODUCT band ("KLM2.11 KLM D3
    NANO DROP 15ML")  ->  customer rows ("TAPAN MEDICO  KOLKATA  6  535.74")
    ->  "TOTAL <qty> <amount>" subtotal.  Each customer row becomes one output
    record (party=customer, area=station, product=current band product).

    Positional: word x0 slices Customer | Station | Qty | Value cleanly, which
    the flat text cannot (customer name and station both run together).
    """
    headers = ["Division", "Party Name", "Area", "Product Name", "Qty", "Amount"]
    if not file_bytes:
        return headers, []

    import pdfplumber

    rows = []
    division = ""
    product = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            linemap = {}
            for w in page.extract_words():
                linemap.setdefault(round(w["top"]), []).append(w)
            for top in sorted(linemap):
                ws = sorted(linemap[top], key=lambda w: w["x0"])
                joined = " ".join(w["text"] for w in ws)
                if _is_furniture(joined):
                    continue

                # --- customer data row: numeric value in the value column + a qty ---
                val_words = [w for w in ws if w["x0"] >= _VAL_X and _VAL_RE.match(w["text"])]
                qty_words = [w for w in ws if _QTY_X <= w["x0"] < _VAL_X and _QTY_RE.match(w["text"])]
                if val_words and qty_words:
                    name = " ".join(w["text"] for w in ws if w["x0"] < _STATION_X).strip()
                    station = " ".join(
                        w["text"] for w in ws if _STATION_X <= w["x0"] < _QTY_X
                    ).strip()
                    if not name:
                        continue
                    qty = _num(qty_words[-1]["text"])
                    amt = _num(val_words[-1]["text"])
                    rows.append([division, name, station, product, qty, amt])
                    continue

                # --- band line (no value column) ---
                tok0 = ws[0]["text"]
                if _CODE_RE.match(tok0) and len(ws) > 1:
                    # product band: name = everything after the code token
                    parts = [w["text"] for w in ws[1:]]
                    # collapse a trailing duplicated pack token ("... 15ML 15ML")
                    if len(parts) >= 2 and parts[-1] == parts[-2] and _PACKISH.search(parts[-1]):
                        parts = parts[:-1]
                    product = " ".join(parts).strip()
                elif re.search(r"[A-Za-z]", joined):
                    # division / company band
                    division = joined.strip()
    return headers, rows
