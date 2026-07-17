"""
"Item Wise - Customer Wise Sale" — SAI KRISHNA AGENCIES / KLM XLSX export.

Layout (band = ITEM, detail rows = CUSTOMERS):

    SAI KRISHNA AGENCIES
    D.NO:...
    Item Wise - Customer Wise Sale
    From: 01-Jun-26  To: 30-Jun-26  KLM COSMO JUN 26
      | CODE | CUSTOMER | QTY | FREE | AMOUNT | ADDRESS | MOBILE | DLNO | CITY | LAST SRATE
    Item  :EKRAN 30 SILICON SUNSCREEN GEL 30GM    PACK  :30GM     <- product band (col0 only)
      | 477388 | SAI SAMPATH MEDS(...) | 3 | 0 | 956.43 | OPP:... | 998... | 755/... | VISAKHAPATNAM | 335.59
    Total: | | | 3 | 0 | 956.43 | | | | |                        <- per-item subtotal (skip)
    Item  :EKRAN SOFT SILICON SUNSCREEN GEL    PACK  :50GM
      | 14121 | SRI SATISH MED&GEN ST(K.G.H) | 1 | 0 | 517.42 | ... | ...

The product is a *band* row ("Item  :<name>    PACK  :<pack>") carried down onto every
customer detail row until the next band. The header column set (CODE/CUSTOMER/QTY/
FREE/AMOUNT/ADDRESS/MOBILE/DLNO/CITY/LAST SRATE) is unusual, so the generic tabular
reader fails to map party_name and the band text leaks into every field (fmt=None).

Gated on the compact title token "itemwisecustomerwisesale" + the exact CUSTOMER/QTY/
AMOUNT header, so it claims only this report.
"""
import re

from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, compact, is_subtotal

_ITEM_BAND_RE = re.compile(r"^\s*item\s*:", re.IGNORECASE)
_PACK_RE = re.compile(r"pack\s*:\s*(.+?)\s*$", re.IGNORECASE)
_TITLE_TOKEN = "itemwisecustomerwisesale"


def _title_present(rows):
    blob = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    return _TITLE_TOKEN in blob


def _header_idx(rows):
    """Row index of the CODE|CUSTOMER|QTY|FREE|AMOUNT header."""
    for idx, row in enumerate(rows[:15]):
        toks = {normalize(cell_text(c)) for c in row if cell_text(c)}
        if "customer" in toks and "qty" in toks and "amount" in toks:
            return idx
    return None


def _cols(header):
    col = {}
    for j, cell in enumerate(header):
        n = normalize(cell_text(cell))
        if n == "code":
            col["code"] = j
        elif n == "customer" and "party_name" not in col:
            col["party_name"] = j
        elif n == "qty":
            col["qty"] = j
        elif n == "free":
            col["free_qty"] = j
        elif n == "amount":
            col["amount"] = j
        elif n == "address":
            col["party_location"] = j
        elif n == "mobile":
            col["raw_mobile"] = j
        elif n == "dlno":
            col["raw_dlno"] = j
        elif n == "city":
            col["raw_city"] = j
        elif n.replace(" ", "") in ("lastsrate", "srate"):
            # "LAST SRATE" is a reference last-sale rate, NOT this line's unit rate; keep
            # it as raw so it never contaminates qty*rate==amount checks.
            col["last_srate"] = j
    return col


def _item_from_band(text):
    """Split 'Item  :<name>    PACK  :<pack>' into (product_name, pack)."""
    s = re.sub(r"^\s*item\s*:", "", text, flags=re.IGNORECASE).strip()
    pack = ""
    m = _PACK_RE.search(s)
    if m:
        pack = m.group(1).strip()
        s = s[: m.start()].strip()
    # a stray trailing 'PACK' keyword with no colon
    s = re.sub(r"\s*pack\s*$", "", s, flags=re.IGNORECASE).strip()
    return s.strip(), pack


def detect(rows):
    if not _title_present(rows):
        return False
    header_idx = _header_idx(rows)
    if header_idx is None:
        return False
    col = _cols(rows[header_idx])
    if "party_name" not in col or "qty" not in col:
        return False
    # confirm at least one Item band + one customer detail row exist
    bands = details = 0
    for raw in rows[header_idx + 1 : header_idx + 200]:
        first = cell_text(raw[0]) if raw else ""
        if _ITEM_BAND_RE.match(first):
            bands += 1
            continue
        pn = col.get("party_name")
        name = cell_text(raw[pn]) if (pn is not None and pn < len(raw)) else ""
        if name and not is_subtotal(name):
            details += 1
    return bands >= 1 and details >= 1


def parse_item_customerwise_sale(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}
    col = _cols(rows[header_idx])

    def _val(cells, key):
        i = col.get(key)
        return cells[i] if (i is not None and i < len(cells)) else ""

    records = []
    current_product = ""
    current_pack = ""
    for raw in rows[header_idx + 1 :]:
        cells = [cell_text(c) for c in raw]
        first = cells[0].strip() if cells else ""

        if _ITEM_BAND_RE.match(first):
            current_product, current_pack = _item_from_band(first)
            continue

        name = _val(cells, "party_name").strip()
        if not name or is_subtotal(name):
            # 'Total:' subtotal row (name blank, first col == 'Total:') -> skip
            continue
        if first and is_subtotal(first):
            continue
        if not current_product:
            continue

        amount = _val(cells, "amount")
        qty = _val(cells, "qty")
        record = {
            "party_name": name,
            "product_name": current_product,
            "qty": qty,
            "free_qty": _val(cells, "free_qty"),
            "amount": amount,
            # No taxable/net column in this export; the Amount is the line net value.
            "taxable_value": amount,
        }
        if current_pack:
            record["pack"] = current_pack
        # Derive the effective unit rate from Amount / Qty (no per-line rate column;
        # "LAST SRATE" is a reference figure, not this transaction's rate).
        try:
            a = float(str(amount).replace(",", "")) if str(amount).strip() else None
            q = float(str(qty).replace(",", "")) if str(qty).strip() else None
            if a is not None and q:
                record["rate"] = round(a / q, 4)
        except (TypeError, ValueError):
            pass
        loc = _val(cells, "party_location")
        if loc:
            record["party_location"] = loc
        city = _val(cells, "raw_city")
        if city:
            record["raw_city"] = city
        mob = _val(cells, "raw_mobile")
        if mob:
            record["raw_mobile"] = mob
        dl = _val(cells, "raw_dlno")
        if dl:
            record["raw_dlno"] = dl
        lsr = _val(cells, "last_srate")
        if lsr:
            record["last_srate"] = lsr
        records.append(record)

    detected = {
        "CODE": "code", "CUSTOMER": "party_name", "QTY": "qty", "FREE": "free_qty",
        "AMOUNT": "amount", "ADDRESS": "party_location", "MOBILE": "raw_mobile",
        "DLNO": "raw_dlno", "CITY": "raw_city", "LAST SRATE": "last_srate",
    }
    return records, detected
