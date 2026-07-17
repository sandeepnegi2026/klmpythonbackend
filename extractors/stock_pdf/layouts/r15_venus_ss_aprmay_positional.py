"""VENUS PHARMA (Ahmedabad) KLM 'Stock and Sales report' with an Apr/May prev-month
pair and a sparse right-aligned movement block (Statment of KLM June_26.PDF).

TARGET REPO PATH: extractors/stock_pdf/layouts/r15_venus_ss_aprmay_positional.py

Header (one physical row, identical to the BHAGYODAY Mar/Apr export except the
month pair):
    Item Name  Pack  Apr  May  Op.  Pur  SP  Sale  SS  SVal  Cr.  Db.  Adj.  C Stk  C Val  Ord.

Column meaning / reconcile mapping (same ERP as klm_ss_marapr_positional):
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
    Apr / May are PREVIOUS-month sales qtys (informational) -> ignored.
    Ord.  -> pending order qty  -> order_qty (kept OUT of closing_stock_value).

Why a POSITIONAL parser and not the existing `venus_stock_statement`:
    All 14 numeric columns are independently BLANKABLE and the numbers are
    right-aligned, so the flat number list has a VARIABLE length per row and the
    dense token-order binding in venus_stock_statement mislabels most rows
    (e.g. AMOCLAFIX 'Op 35 | Sale 10 | SVal 1463 | CStk 25 | CVal 3291' is read
    as opening=35, purchase=10, sales_qty=1463, closing=25 -> 6.6% reconcile).
    We read word x-positions with pdfplumber and bucket each number into its
    column by x-centre against the printed header anchors (self-calibrating,
    the header repeats on every page).

Venus-specific handling (differs from klm_ss_marapr_positional):
    * Division bands print as 'KLM LABORETIRES-COSMOCOR XA0000' /
      'KLM LABORATORIES-PEDIA-170' (no 'DIVISION' word) -> ^KLM LAB prefix,
      trailing X-code dropped (it renders right of the name region).
    * Every page repeats the letterhead: 'VENUS PHARMA.' (name-only) and the
      street address '37, CELLER, ... Ph:97127 22022. 97378 22022' whose phone
      numbers land inside the movement band -> both skipped by name shape.
    * Rows are single-line: there is NO wrapped-name continuation fold (the
      fold in the Mar/Apr sibling swallowed Venus page headers into names).
    * 'Ord.' is anchored so pending-order qtys cannot clobber closing_stock_value.

GATE (detect.py, immediately AFTER the klm_ss_marapr_positional gate):
    if "cr.db.adj.cstkcval" in _c15 and "aprmayop." in _c15 and "dec" not in low:
        return "venus_ss_aprmay_positional"
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")

# Header tokens that anchor each numeric column. 'C Stk' / 'C Val' render as
# separate words and are matched by their 'C' clusters below.
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
    c_tokens = sorted(
        (w for w in words if w["text"] == "C"), key=lambda w: w["x0"]
    )
    stk = next((w for w in words if w["text"] == "Stk"), None)
    val = next((w for w in words if w["text"] == "Val"), None)
    if not (c_tokens and stk and val):
        return None
    cstk_x = (c_tokens[0]["x0"] + stk["x1"]) / 2.0
    cval_x = (c_tokens[-1]["x0"] + val["x1"]) / 2.0
    anchors = {
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
    # 'Ord.' (pending order) sits right of C Val; without its own anchor an Ord
    # number would be nearest-bucketed onto closing_value and clobber it.
    if "Ord." in labels:
        anchors["order_qty"] = labels["Ord."]
    return anchors


# Venus division band: 'KLM LABORETIRES-COSMOCOR' / 'KLM LABORATORIES-PEDIA-170'
# (both spellings appear in the same file). Real products may start with 'KLM '
# ('KLM D3 60K CAP', 'KLM C 1000 TAB') but never 'KLM LAB'.
_DIVISION_BAND = re.compile(r"^KLM\s+LAB", re.I)
_SKIP_PREFIX = re.compile(
    r"^(Opening Value|Closing Value|Sales\s*:|Sales Value|Report Date|Purchase Value"
    r"|Credit|Debit|Adjustment|Page|MG\d|MF\d|Item Name|Stock and Sales"
    r"|VENUS|\d+,)",
    re.I,
)


def parse_r15_venus_ss_aprmay_positional(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        division = ""
        for page in pdf.pages:
            # The header repeats on every page BELOW the letterhead (vendor
            # name / street address with phone numbers). Re-anchoring per page
            # means letterhead rows can never be parsed as data.
            anchors = None
            ordered = None  # (field, x-centre) pairs for nearest-centre bucketing
            words = page.extract_words()
            for row_words in _cluster_rows(words):
                row_words = sorted(row_words, key=lambda w: w["x0"])
                found = _header_anchors(row_words)
                if found:
                    anchors = found
                    ordered = [(k, x) for k, x in found.items()]
                    continue
                if anchors is None:
                    continue

                # Numbers left of the Op. column are the informational Apr/May
                # prev-month qtys -> excluded from cells. Pack tokens sit in a
                # narrow band right of the name; numeric pack fragments ('2' of
                # '2 ML', '50' of '50 G') start well left of the Apr column's
                # right-aligned digits, so x0 < 170 keeps them without leaking
                # Apr values (their x0 is >= ~189).
                num_min = anchors["opening"] - 18
                name_toks, pack_toks, cells = [], [], {}
                for w in row_words:
                    cx = _center(w)
                    if _is_num(w["text"]) and cx >= num_min:
                        col = min(ordered, key=lambda o: abs(o[1] - cx))[0]
                        cells[col] = _to_f(w["text"])
                    elif w["x0"] < 135:
                        # numeric tokens here are part of the NAME
                        # ('AMOCLAFIX 625', 'KLCEPO 200', 'RESOTEN 10')
                        name_toks.append(w["text"])
                    elif w["x0"] < 170:
                        # pack fragments, incl. numeric ones ('2' of '2 ML',
                        # '50' of '50 G'); Apr-column digits right-align with
                        # x0 >= ~180 so they cannot leak in here
                        pack_toks.append(w["text"])
                    elif w["x0"] < 190 and not _is_num(w["text"]):
                        pack_toks.append(w["text"])

                name = " ".join(name_toks).strip()
                low = name.lower()

                # Division band -> record & skip (X-code renders right of the
                # name region, but strip defensively).
                if _DIVISION_BAND.match(name) and not cells and not pack_toks:
                    division = re.sub(r"\s+X[A-Z]\d+$", "", name).strip()
                    continue
                if _SKIP_PREFIX.match(name):
                    continue
                if "total" in low and not pack_toks:
                    continue
                # Venus rows are single-line: name-only lines are letterhead /
                # noise, never wrapped continuations -> drop (no fold).
                if not cells or not name:
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
                    # Adj. is a signed stock adjustment; fold it into the
                    # +sales_return reconcile slot so
                    # opening+..+sales_return+adj = closing holds.
                    "sales_return": sr + adj,
                    "sales_value": cells.get("sales_value", 0.0),
                    "closing_stock": cstk,
                    "closing_stock_value": cells.get("closing_value", 0.0),
                    "order_qty": cells.get("order_qty", 0.0),
                })
    return records
