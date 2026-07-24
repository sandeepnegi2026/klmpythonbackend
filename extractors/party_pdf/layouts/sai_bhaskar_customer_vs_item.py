import io
import re

import pdfplumber

# SAI BHASKAR MEDICAL DISTRIBUTORS "Customer VS Item Details".
#
# Party-banded ("<PARTY>,<TOWN>") with per-party "Totals" footers and a final
# "Grand Total" line. Header: Item name Town Bill Date Bill No. Batch No Qty Free
# Rate Net Value. The Rate column is OPTIONAL (fully-free/promo rows omit it), so
# token order is unreliable — the four right-aligned numeric columns are assigned
# POSITIONALLY by their right edge (x1) band. A row is emitted only if it carries a
# Net Value token; rows without one (free/qty continuation halves of a split
# invoice, or fully-free promo lines) carry no sale value and are dropped, so
# sum(Net Value) reconciles EXACTLY to each party "Totals" and to the Grand Total.
#
# Positional: needs word x-coordinates, so the parser re-opens the PDF bytes.

_NUMRE = re.compile(r"^-?[\d,]+\.\d{2}$")
_DATERE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_CONTDRE = re.compile(r"\s*\(Contd\.?,?\)\s*$", re.I)

# right-edge (x1) windows for the four right-aligned numeric columns
_BANDS = [("qty", 525, 535), ("free", 605, 615), ("rate", 685, 695), ("net", 765, 775)]


def _num(s):
    return float(s.replace(",", ""))


def _band_of(x1):
    for name, lo, hi in _BANDS:
        if lo <= x1 <= hi:
            return name
    return None


def _cluster_lines(words, ytol=4):
    """Group words into logical lines with a 4px top tolerance: item text sits a
    few px above its own numbers, and a naive round(top) grouping would split a
    'Totals' label from its numbers and double-count it as a data row."""
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    clusters = []
    for w in ws:
        if clusters and abs(w["top"] - clusters[-1][0]) <= ytol:
            clusters[-1][1].append(w)
            clusters[-1][0] = w["top"]
        else:
            clusters.append([w["top"], [w]])
    return [sorted(c[1], key=lambda x: x["x0"]) for c in clusters]


def parse_sai_bhaskar_customer_vs_item(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Invoice Date",
               "Invoice No", "Qty", "Free", "Rate", "Amount"]
    rows = []
    if not file_bytes:
        return headers, rows

    party = ""
    party_town = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            last_row = None   # last emitted row (dict), for product/town wrap continuation
            for ws in _cluster_lines(page.extract_words(use_text_flow=False)):
                texts = [w["text"] for w in ws]
                joined = " ".join(texts)
                first = ws[0]
                if joined.startswith(("SAI BHASKAR", "ALLURI", "Customer VS Item", "Page ")):
                    continue
                if texts[0] == "Item" and "name" in texts:
                    continue
                nums = [w for w in ws if _NUMRE.match(w["text"]) and _band_of(w["x1"])]
                # Grand Total / per-party Totals footers (oracles) — skip
                if (texts[0] == "Grand" and len(texts) > 1 and texts[1] == "Total") \
                        or texts[0] == "Totals":
                    last_row = None
                    continue
                has_billdate = any(_DATERE.match(t) for t in texts)
                if not nums:
                    lefttext = joined.strip()
                    # party band "<PARTY>,<TOWN>"; strip "(Contd.,)" so continued rows fold in
                    if first["x0"] < 50 and "," in lefttext and not has_billdate:
                        party = _CONTDRE.sub("", lefttext).strip()
                        party_town = party[party.rfind(",") + 1:].strip()
                        last_row = None
                        continue
                    # product-name wrap continuation (indented item column)
                    if last_row is not None and first["x0"] < 170:
                        last_row["product"] = (last_row["product"] + " " + lefttext).strip()
                        continue
                    # town wrap continuation (e.g. 'SINGARAYAKOND' + 'A')
                    if last_row is not None and 175 <= first["x0"] < 262:
                        last_row["loc"] = (last_row["loc"] + lefttext).strip()
                        continue
                    continue
                # data line: numeric cols assigned purely by x1 band (Rate optional)
                colvals = {_band_of(w["x1"]): _num(w["text"]) for w in nums}
                if "net" not in colvals:
                    # no sale value (split-invoice half / fully-free row) — drop
                    last_row = None
                    continue
                nonnum = [w for w in ws if not (_NUMRE.match(w["text"]) and _band_of(w["x1"]))]
                item_words = [w for w in nonnum if w["x0"] < 175]
                town_words = [w for w in nonnum if 175 <= w["x0"] < 262]
                date = next((w["text"] for w in nonnum if _DATERE.match(w["text"])), "")
                bnw = sorted([w for w in nonnum if 320 <= w["x0"] < 405], key=lambda x: x["x0"])
                billno = " ".join(w["text"] for w in bnw)
                last_row = {
                    "party": party,
                    "loc": " ".join(w["text"] for w in town_words) or party_town or "",
                    "product": " ".join(w["text"] for w in item_words).strip(),
                    "date": date,
                    "bill": billno,
                    "qty": colvals.get("qty", ""),
                    "free": colvals.get("free", ""),
                    "rate": colvals.get("rate", ""),
                    "net": colvals["net"],
                }
                rows.append(last_row)

    out = [[r["party"], r["loc"], r["product"], r["date"], r["bill"],
            r["qty"], r["free"], r["rate"], r["net"]] for r in rows]
    return headers, out
