import io
import re

import pdfplumber

from extractors.stock_pdf.parse_common import _skip_line, _split_product_pack

# One data row: <lead> <MM/YY exp> Opening Receipts Total Sales ClosingStock ClosingValue
# The lead (product name + packing + BATCH, batch tokens may contain spaces) is
# split into fields positionally when file_bytes is available; otherwise a flat
# best-effort split is used. Reconciliation depends only on the six trailing
# numbers, all captured from the flat text — so it holds with or without bytes.
_ROW_RE = re.compile(
    r"^(?P<lead>.+?)\s+(?P<exp>\d{1,2}/\d{2,4})\s+"
    r"(?P<opening>-?\d+)\s+(?P<receipts>-?\d+)\s+(?P<total>-?\d+)\s+"
    r"(?P<sales>-?\d+)\s+(?P<closing>-?\d+)\s+(?P<clvalue>-?[\d,]+\.\d{2})$"
)

# Division band: 'Company Name : KLM(PHARMA DIVISION)' / 'KLM{COSMOCOR}' / 'KLM(COSMO Q)'
_DIV_RE = re.compile(r"Company Name\s*:\s*KLM\s*[\(\{\[]?\s*([^)}\]]+?)\s*[\)\}\]]?\s*(?:Page\s*:.*)?$", re.I)


def _to_num(t):
    t = t.replace(",", "").strip()
    try:
        return float(t)
    except ValueError:
        return 0.0


def _clean_div(raw):
    d = raw.strip()
    # 'PHARMA DIVISION' -> 'PHARMA'; leave 'COSMO Q', 'DERMACOR D2', 'COSMOCOR' intact.
    d = re.sub(r"\s+DIVISION$", "", d, flags=re.I).strip()
    return d


def _build_lead_anchors(file_bytes):
    """Read the header word x0 positions (Packing/BATCH/EXP) so the lead can be
    split into product / pack / batch even when batch tokens contain spaces.
    Returns (pack_x0, batch_x0, exp_x0) or None."""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                words = page.extract_words(x_tolerance=1.5, y_tolerance=3)
                labels = {w["text"].lower(): w["x0"] for w in words}
                if {"packing", "batch", "exp"} <= labels.keys():
                    return labels["packing"], labels["batch"], labels["exp"]
    except Exception:
        return None
    return None


def _positional_leads(file_bytes, pack_x, batch_x, exp_x):
    """Map each data-row lead text -> (product_name, pack, batch_no) using word
    x-positions. Keyed by the joined lead text so the flat row loop can look it
    up. Multiple rows can share the same lead text (real batch splits print the
    same product+pack+batch); we store a list per lead and pop in order."""
    leads = {}
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                words = page.extract_words(x_tolerance=1.5, y_tolerance=3)
                rows = {}
                for w in words:
                    rows.setdefault(round(w["top"]), []).append(w)
                for _, ws in sorted(rows.items()):
                    ws = sorted(ws, key=lambda w: w["x0"])
                    # a data row carries a numeric value at/after Opening column
                    if not any(
                        w["x0"] >= exp_x - 2 and re.match(r"^-?[\d,]+\.?\d*$", w["text"])
                        for w in ws
                    ):
                        continue
                    name = [w["text"] for w in ws if w["x0"] < pack_x - 2]
                    pack = [w["text"] for w in ws if pack_x - 2 <= w["x0"] < batch_x - 2]
                    batch = [w["text"] for w in ws if batch_x - 2 <= w["x0"] < exp_x - 2]
                    if not name:
                        continue
                    lead_text = " ".join(name + pack + batch)
                    leads.setdefault(lead_text, []).append(
                        (" ".join(name), " ".join(pack), " ".join(batch))
                    )
    except Exception:
        return {}
    return leads


def _flat_lead_split(lead):
    """Fallback split when no bytes: last token is BATCH, then peel a pack via
    _split_product_pack. Batches with embedded spaces cannot be recovered flat."""
    toks = lead.split()
    if len(toks) >= 2:
        batch = toks[-1]
        name_pack = " ".join(toks[:-1])
    else:
        batch = ""
        name_pack = lead
    name, pack = _split_product_pack(name_pack)
    return name, pack, batch


def parse_stock_batchwise_statement(text, file_bytes=None):
    """SRI VASAVI 'STOCK AND SALES STATEMENT' — batch-wise KLM division export.

    Columns: Product Name | Packing | BATCH | EXP | Opening | Receipts | Total |
    Sales | Closing Stock | Closing Value.  One row per product+batch; identical
    rows are real batch splits and are NOT deduped.

    Reconciliation (verified 333/333): closing == opening + receipts - sales and
    total == opening + receipts.  Only closing_stock_value (rupees) is comparable
    to the per-division 'Closing Value Rs.' footer totals.
    """
    lead_map = None
    if file_bytes:
        anchors = _build_lead_anchors(file_bytes)
        if anchors:
            lead_map = _positional_leads(file_bytes, *anchors)

    records = []
    division = ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        dm = _DIV_RE.search(s)
        if dm:
            division = _clean_div(dm.group(1))
            continue
        m = _ROW_RE.match(s)
        if not m:
            continue
        lead = m.group("lead").strip()
        if _skip_line(lead):
            continue

        product_name = pack = batch_no = ""
        if lead_map is not None and lead_map.get(lead):
            product_name, pack, batch_no = lead_map[lead].pop(0)
        else:
            product_name, pack, batch_no = _flat_lead_split(lead)

        rec = {
            "product_name": product_name,
            "pack": pack,
            "batch_no": batch_no,
            "expiry": m.group("exp"),
            "opening_stock": _to_num(m.group("opening")),
            "purchase_stock": _to_num(m.group("receipts")),
            "total_stock": _to_num(m.group("total")),
            "sales_qty": _to_num(m.group("sales")),
            "closing_stock": _to_num(m.group("closing")),
            "closing_stock_value": _to_num(m.group("clvalue")),
        }
        if division:
            rec["division"] = division
        records.append(rec)
    return records
