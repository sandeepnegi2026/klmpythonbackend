"""KLM ERP single-page 'Stock and Sales report' with a Mar/Apr prev-month pair and
a sparse right-aligned movement block (BHAGYODAY AGENCIES -> KLM PHARMA.PDF).

Header (one physical row):
    Item Name  Pack  Mar  Apr  Op.  Pur  SP  Sale  SS  SVal  Cr.  Db.  Adj.  C Stk  C Val  Ord.

Column meaning / reconcile mapping:
    Op.   -> opening_stock
    Pur   -> purchase_stock
    SP    -> purchase_free      (scheme / free purchase, stock inflow)
    Db.   -> purchase_return    (Debit-Note qty to supplier, stock OUTflow)
    Sale  -> sales_qty
    SS    -> sales_free         (scheme / free sale, stock OUTflow)
    Cr.   -> sales_return       (Credit-Note qty from customer, stock inflow)
    Adj.  -> signed adjustment  (folded into the +sales_return slot)
    SVal  -> sales_value        (value; NEVER used as a quantity)
    C Stk -> closing_stock
    C Val -> closing_stock_value
    Mar / Apr are PREVIOUS-month sales qtys (informational) -> ignored.
    Ord.  -> pending order qty (informational) -> ignored.
Reconcile (verified on every data row of the sample):
    opening + purchase + purchase_free - purchase_return
             - sales_qty - sales_free + sales_return + adjustment = closing

Why a POSITIONAL parser and not the existing `venus_stock_statement`:
    Venus prints every cell densely (Dec/Jan prev-months, all movement cells filled),
    so its flat-token positional index works. This export leaves interior movement
    cells BLANK and right-aligns the numbers, so the flat number list has a VARIABLE
    length per row and `venus_stock_statement` mis-binds every column (opening/purchase/
    closing come back null, SVal lands in sales_free, Db/Adj land in sales_value).
    We read word x-positions with pdfplumber and bucket each number into its column by
    x-centre against the printed header anchors.

GATE TOKEN (compact, spaces stripped, lowercased), unique to this export's header:
    'sppssvalcr.db.adj.' followed by the closing pair -> 'sppssvalcr.db.adj.'
    (the SP|Sale|SS|SVal|Cr.|Db.|Adj. run). Combined with 'cstk' + 'stockandsalesreport'
    it is disjoint from the Venus (Dec/Jan) and pharmassist page-split siblings.
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")

# Header tokens that anchor each numeric column. Text may render 'C Stk' / 'C Val'
# as two words, so those are matched by their leading 'C' cluster below.
_ANCHOR_TOKENS = ("Op.", "Pur", "SP", "Sale", "SS", "SVal", "Cr.", "Db.", "Adj.")


def _is_num(t):
    t = t.rstrip(".")
    return bool(t) and bool(_NUM_RE.fullmatch(t.replace(",", ""))) and any(
        c.isdigit() for c in t
    )


def _to_f(t):
    t = t.rstrip(".").replace(",", "")
    try:
        return float(t)
    except ValueError:
        return 0.0


def _center(w):
    return (w["x0"] + w["x1"]) / 2.0


def _cluster_rows(words, tol=4):
    """Group words into visual rows: tops within `tol` px belong together."""
    by_top = {}
    for w in words:
        by_top.setdefault(round(w["top"]), []).append(w)
    rows, cur, start = [], [], None
    for top in sorted(by_top):
        if start is None or top - start <= tol:
            if start is None:
                start = top
            cur.extend(by_top[top])
        else:
            rows.append(cur)
            cur, start = list(by_top[top]), top
    if cur:
        rows.append(cur)
    return rows


def _header_anchors(words):
    """Return column x-centres if this visual row is the movement header, else None."""
    labels = {}
    for w in words:
        labels.setdefault(w["text"], _center(w))
    if not all(tok in labels for tok in _ANCHOR_TOKENS):
        return None
    # C Stk / C Val: the two 'C' clusters (closing qty then closing value). Take the
    # right-most two 'C' tokens' centres shifted toward their 'Stk'/'Val' partner.
    c_tokens = sorted(
        (w for w in words if w["text"] == "C"), key=lambda w: w["x0"]
    )
    stk = next((w for w in words if w["text"] == "Stk"), None)
    val = next((w for w in words if w["text"] == "Val"), None)
    if not (c_tokens and stk and val):
        return None
    cstk_x = (c_tokens[0]["x0"] + stk["x1"]) / 2.0
    cval_x = (c_tokens[-1]["x0"] + val["x1"]) / 2.0
    return {
        "opening": labels["Op."],
        "purchase": labels["Pur"],
        "purchase_free": labels["SP"],
        "sales_qty": labels["Sale"],
        "sales_free": labels["SS"],
        "sales_value": labels["SVal"],
        "sales_return": labels["Cr."],   # Credit note (customer return) -> inflow
        "purchase_return": labels["Db."],  # Debit note (to supplier) -> outflow
        "adj": labels["Adj."],
        "closing": cstk_x,
        "closing_value": cval_x,
    }


_DIVISION_BAND = re.compile(r"^KLM\b.*DIVISION", re.I)
_SKIP_PREFIX = re.compile(
    r"^(Opening Value|Closing Value|Sales\s*:|Sales Value|Report Date|Purchase Value"
    r"|Credit|Debit|Adjustment|Page|MG\d|MF\d|Item Name|Stock and Sales)",
    re.I,
)


def parse_r15_klm_stock_sales_marapr_positional(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        anchors = None
        division = ""
        # Column x-centres, ordered left->right, for nearest-centre bucketing.
        ordered = None
        for page in pdf.pages:
            words = page.extract_words()
            for row_words in _cluster_rows(words):
                row_words = sorted(row_words, key=lambda w: w["x0"])
                found = _header_anchors(row_words)
                if found:
                    anchors = found
                    ordered = [
                        ("opening", found["opening"]),
                        ("purchase", found["purchase"]),
                        ("purchase_free", found["purchase_free"]),
                        ("sales_qty", found["sales_qty"]),
                        ("sales_free", found["sales_free"]),
                        ("sales_value", found["sales_value"]),
                        ("sales_return", found["sales_return"]),
                        ("purchase_return", found["purchase_return"]),
                        ("adj", found["adj"]),
                        ("closing", found["closing"]),
                        ("closing_value", found["closing_value"]),
                    ]
                    continue
                if anchors is None:
                    continue

                # Split name/pack from numbers. The Pack column sits immediately right
                # of the name; the Mar/Apr prev-month qty columns (informational) live
                # between Pack and the Op. column, so numbers there must NOT leak into
                # pack. pack_max is midway between the Pack column and the Mar column.
                num_min = anchors["opening"] - 18
                # Pack tokens render just right of the name and left of the Mar/Apr
                # prev-month qty columns; 190px keeps pack clean of those qty cells.
                pack_max = 190.0
                name_toks, pack_toks, cells = [], [], {}
                for w in row_words:
                    cx = _center(w)
                    if _is_num(w["text"]) and cx >= num_min:
                        col = min(ordered, key=lambda o: abs(o[1] - cx))[0]
                        cells[col] = _to_f(w["text"])
                    elif w["x0"] < 135:
                        name_toks.append(w["text"])
                    elif w["x0"] < pack_max and not _is_num(w["text"]):
                        pack_toks.append(w["text"])

                name = " ".join(name_toks).strip()
                low = name.lower()

                # Division band ("KLM PHARMA DIVISION ...") -> record & skip.
                if _DIVISION_BAND.match(name) and not cells:
                    division = re.sub(r"\s+X[A-Z]\d+$", "", name).strip()
                    continue
                if _SKIP_PREFIX.match(name) or _SKIP_PREFIX.match(low):
                    continue
                if "total" in low and not pack_toks:
                    continue

                if not cells:
                    # name-only line: a wrapped continuation of the previous product
                    # (no pack, no numbers) folds back; otherwise it is a zero-movement
                    # product row we drop.
                    if name and not pack_toks and records:
                        records[-1]["product_name"] = (
                            records[-1]["product_name"] + " " + name
                        ).strip()
                    continue
                if not name:
                    continue

                op = cells.get("opening", 0.0)
                pur = cells.get("purchase", 0.0)
                pf = cells.get("purchase_free", 0.0)
                pr = cells.get("purchase_return", 0.0)
                sq = cells.get("sales_qty", 0.0)
                sf = cells.get("sales_free", 0.0)
                sr = cells.get("sales_return", 0.0)
                adj = cells.get("adj", 0.0)
                cstk = cells.get("closing", 0.0)

                # drop all-blank phantom rows (only a value cell, no movement/closing)
                if not any((op, pur, pf, pr, sq, sf, sr, adj, cstk)):
                    continue

                records.append({
                    "product_name": name,
                    "pack": " ".join(pack_toks).strip(),
                    "division": division,
                    "opening_stock": op,
                    "purchase_stock": pur,
                    "purchase_free": pf,
                    "purchase_return": pr,
                    "sales_qty": sq,
                    "sales_free": sf,
                    # Adj. is a signed stock adjustment; fold it into the +sales_return
                    # reconcile slot so opening+..+sales_return+adj = closing holds.
                    "sales_return": sr + adj,
                    "sales_value": cells.get("sales_value", 0.0),
                    "closing_stock": cstk,
                    "closing_stock_value": cells.get("closing_value", 0.0),
                })
    return records
