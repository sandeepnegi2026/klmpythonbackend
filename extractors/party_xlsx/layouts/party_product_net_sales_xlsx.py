"""
Marg ERP 9+ "Party/Product Wise Net Sales" export (seen from BADAL ENTERPRISE / KLM).

The .xls is the MARG "MARG ERP 9+ Excel Report" sheet. Structure::

    M/S BADAL ENTERPRISE                                   <- M/S header block
    49,NETAJI SARANI, HAIDERPARA,SILIGURI, ...
    Phone : ...  E-Mail : ...
    GSTIN : 19AUMPS0941G1ZB
    Party/Product Wise Net Sales From 01-06-2026 To 30-06-2026   <- title
    Party/Product Name | Sale Qty | Ret Qty | Net Qty      <- header row
    PRIME TARDERS 23-24                                    <- party band (col0 only, qty cells blank)
    COSMO Q CONDITIONER 150GM | 20 | 0 | 20               <- product line
    RESOTEN 20 10STRIP        | 120 | 0 | 120
    ...
    Party Total | 2864 | 0 | 2864                          <- party subtotal (skip)
    Grand Total | 2864 | 0 | 2864                          <- grand total (skip)

The party name sits in a *band row* (column 0 only, the three qty columns blank), not
in a column. Product lines carry three numeric cells: Sale Qty (-> qty), Ret Qty
(-> return_qty), Net Qty (= Sale - Ret, derived, not stored). There is NO amount / rate
/ value / free column, so the value dimension is intentionally left empty (the file
lands GREEN on qty/party/product and correctly AMBER on value).

The header maps only two canonical keys (Party/Product Name, Sale Qty) because Ret/Net
Qty do not map, so ``detect_header_row(min=3/4)`` never fires and neither ``tabular``
nor the other band readers claim this file. Detection is gated hard on the distinctive
title ("Party/Product Wise Net Sales") plus the exact header tokens, so no currently
working file is diverted.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

# Compact (normalize + no-space) title fingerprint unique to this Marg export.
_TITLE_SIG = "partyproductwisenetsales"
# The four header cells, in compact form.
_HDR_NAME = "partyproductname"
_HDR_SALE = "saleqty"
_HDR_RET = "retqty"
_HDR_NET = "netqty"

# Total / footer rows to skip (they carry the three qty cells like a product line).
_TOTAL_RE = re.compile(r"^\s*(party\s*total|grand\s*total|net\s*total|total)\b", re.IGNORECASE)
# Repeated per-page header/footer noise (the M/S block reprints on every page break).
_SKIP_RE = re.compile(
    r"^\s*(m/s\b|phone\b|gstin\b|e-?mail\b|party/product\s+wise|party/product\s+name|"
    r"continued\.\.|page\s*no|\*+\s*end|from\s*:|report\s+date)",
    re.IGNORECASE,
)


def _is_number(text):
    if text is None:
        return False
    t = str(text).strip()
    if not t:
        return False
    return bool(re.fullmatch(r"-?\d[\d,]*\.?\d*", t))


def _title_row_idx(rows):
    for idx, row in enumerate(rows[:20]):
        if _TITLE_SIG in compact(" ".join(cell_text(c) for c in row)):
            return idx
    return None


def _header_idx(rows):
    """Row index of the ``Party/Product Name | Sale Qty | Ret Qty | Net Qty`` header."""
    for idx, row in enumerate(rows[:25]):
        toks = {compact(cell_text(c)) for c in row if cell_text(c)}
        if _HDR_NAME in toks and _HDR_SALE in toks and _HDR_RET in toks and _HDR_NET in toks:
            return idx
    return None


def detect(rows):
    """True only for the Marg "Party/Product Wise Net Sales" export.

    Requires BOTH the distinctive title fingerprint and the four exact header cells,
    plus at least one bare party band (col0 text, qty cells blank) followed by product
    rows carrying three numeric cells, so a plain columnar file can never be stolen.
    """
    if _title_row_idx(rows) is None:
        return False
    header_idx = _header_idx(rows)
    if header_idx is None:
        return False
    bands = prods = 0
    for raw in rows[header_idx + 1 : header_idx + 200]:
        cells = [cell_text(c) for c in raw]
        first = cells[0].strip() if cells else ""
        if not first or _TOTAL_RE.match(first) or _SKIP_RE.match(first):
            continue
        tail = cells[1:4]
        if any(_is_number(t) for t in tail):
            prods += 1
        elif not any(t.strip() for t in tail):
            bands += 1
    return bands >= 1 and prods >= 2


def parse_party_product_net_sales_xlsx(rows):
    header_idx = _header_idx(rows)
    if header_idx is None:
        return [], {}

    records = []
    current_party = ""
    for raw in rows[header_idx + 1 :]:
        cells = [cell_text(c) for c in raw]
        first = cells[0].strip() if cells else ""
        if not first:
            continue
        # totals / repeated per-page header + footer noise
        if _TOTAL_RE.match(first) or _SKIP_RE.match(first):
            continue

        tail = cells[1:4]
        has_number = any(_is_number(t) for t in tail)

        # band row: col0 has text but the three qty cells are all blank -> new party
        if not has_number and not any(t.strip() for t in tail):
            current_party = first
            continue

        if not has_number:
            # a stray text row that isn't a clean band and isn't a product line
            continue
        if not current_party:
            continue

        sale_qty = tail[0] if len(tail) > 0 else ""
        ret_qty = tail[1] if len(tail) > 1 else ""
        record = {
            "party_name": current_party,
            "product_name": first,
            "qty": sale_qty,
        }
        # Ret Qty -> sales returns (all 0 in the sample, but map it when present).
        if ret_qty and _is_number(ret_qty) and ret_qty.strip() not in ("0", "0.0"):
            record["return_qty"] = ret_qty
        # No amount / rate / free / value column exists in this export; leave the value
        # dimension empty on purpose (the vendor prints no value -> correct soft AMBER).
        records.append(record)

    detected = {
        "Party/Product Name": "product_name",
        "Sale Qty": "qty",
        "Ret Qty": "return_qty",
        "Net Qty": "net_qty",
    }
    return records, detected
