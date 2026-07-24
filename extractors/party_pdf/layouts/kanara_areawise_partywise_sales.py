import io
import re
from collections import defaultdict

import pdfplumber

# KANARA DISTRIBUTOR "Areawise Partywise Sales".
#
# Company / Area bands -> party rows (Name | Product | Packing | Qty | Free | Value).
# Party name is in the leftmost band (x0<127.5) and carries down to product rows that
# omit it. Value (x0>=430) reconciles EXACT to per-party 'Party Total' (83/83); the
# printed grand total is rounded to 1 decimal (vendor rounding, ~2 paisa). Positional:
# re-opens the PDF bytes.

_PARTY_MAX_X = 127.5
_PRODUCT_MAX_X = 279.0
_PACKIN_MAX_X = 320.0
_QTY_MAX_X = 400.0
_FREE_MAX_X = 430.0
_NUM_RE = re.compile(r"^-?\d[\d,]*\.?\d*$")


def _n(s):
    return float(s.replace(",", ""))


def parse_kanara_areawise_partywise_sales(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    if not file_bytes:
        return headers, rows
    area = ""
    cur_party = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines = defaultdict(list)
            for w in page.extract_words(keep_blank_chars=False):
                lines[round(w["top"])].append(w)
            for top in sorted(lines):
                ws = sorted(lines[top], key=lambda w: w["x0"])
                texts = [w["text"] for w in ws]
                joined = " ".join(texts)
                jn = joined.replace(" ", "")
                if joined.startswith("KANARA DISTRIBUTOR") or joined == "MANGALURU":
                    continue
                if joined.startswith("Areawise Partywise"):
                    continue
                if texts[:1] == ["Name"] and "Product" in texts:
                    continue
                if texts[:1] == ["Company"] and texts[1:2] == [":"]:
                    continue
                if texts[:1] == ["Area"] and texts[1:2] == [":"]:
                    area = " ".join(texts[2:])
                    continue
                if texts[:2] == ["Party", "Total"]:
                    cur_party = ""
                    continue
                if texts[:2] == ["Area", "Total"] or jn.startswith("CompanyTotal") or jn.startswith("GrandTotal"):
                    continue                                       # oracles
                party_toks, prod_toks, packin_toks = [], [], []
                qty = free = value = None
                for w in ws:
                    x0, t = w["x0"], w["text"]
                    if x0 < _PARTY_MAX_X:
                        party_toks.append(t)
                    elif x0 < _PRODUCT_MAX_X:
                        prod_toks.append(t)
                    elif x0 < _PACKIN_MAX_X:
                        packin_toks.append(t)
                    else:
                        if not _NUM_RE.match(t):
                            packin_toks.append(t)
                            continue
                        if x0 < _QTY_MAX_X:
                            qty = _n(t)
                        elif x0 < _FREE_MAX_X:
                            free = _n(t)
                        else:
                            value = _n(t)
                if party_toks:
                    cur_party = " ".join(party_toks)
                if value is None:
                    continue
                rows.append([cur_party, area, " ".join(prod_toks), qty, free, value])
    return headers, rows
