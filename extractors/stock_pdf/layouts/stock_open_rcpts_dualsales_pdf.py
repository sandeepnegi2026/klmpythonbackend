"""KLM division 'Stock Report' with dual sales columns (SAI PHARMA, SANGAMNER).

Header (single band, one row per product):
    Item Name | Packg | Open.Stk. | Receipt | L.Sales | Cur.Sls |
    Pur.Rtn | Sls.Rtn | Clos.(Qty & Amt)

The last header cell "Clos.(Qty & Amt)" covers TWO physical columns — the closing
QTY followed by the closing VALUE (rupees) — so every data row carries 8 trailing
numbers even though the header shows 9 label cells:

    [Open, Receipt, L.Sales, Cur.Sls, Pur.Rtn, Sls.Rtn, Clos.Qty, Clos.Amt]

Reconciles exactly on quantity — ONLY Cur.Sls is the current-period outflow;
L.Sales is last-month's sales (informational) and is NOT deducted:
    Clos.Qty = Open + Receipt - Cur.Sls - Pur.Rtn + Sls.Rtn
e.g. APPYBUSH  50 + 0 - 42 = 8  (printed Clos.Qty 8, Amt 858);
     CUTIHEAL  25 + 5 - 4 = 26 (L.Sales 20 is prior-month, ignored).

Traps this parser must survive (why it is POSITIONAL, not flat-token):
  * The trailing Clos.Amt is a rupee VALUE — a flat parser would drop it into
    closing_stock (qty). We map it to closing_stock_value.
  * L.Sales (prior month) and Cur.Sls (current month) are two separate sales
    columns; only Cur.Sls belongs in sales_qty (else stock never reconciles).
    L.Sales is preserved in the non-canonical `prior_month_sales` field.
  * Some rows print a stray number in the Packg column while the real pack text
    ("lot") sits in the name area (Klm C-20 lot 0 ...); some print the pack as a
    bare number (NEVLON XL LOTION 250 ...). Bucketing by the 8 fixed stat-column
    right-edges keeps those out of the numeric fields.
  * Skip the "Grand Total" footer (its single trailing closing number is a total,
    not a per-row value).

The PDF is a fixed-width text export (n_rects == 0); the eight statistic columns
are right-aligned at stable x1 (right-edge) positions, so we bucket each number
token to its column by nearest header anchor.
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")

# Right-edge (x1) anchors of the 8 statistic columns, read off the header/data
# grid of this export. Open.Stk / Receipt / L.Sales are the printed header labels;
# the remaining five are the regularly-spaced (~34.6px) columns that follow.
_ANCHORS = (213.0, 252.0, 292.0, 331.0, 366.0, 400.0, 440.0, 484.0)
_ANCHOR_TOL = 12.0            # a number belongs to a column if |x1 - anchor| <= tol
_STAT_LEFT = _ANCHORS[0] - 40  # numbers with x1 below this are name/pack, not stats
_PACK_MAX_X0 = 165.0           # Packg column sits ~138-163; name is left of ~130
_NAME_MAX_X0 = 130.0


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _cluster_rows(words, tol=4):
    """Group words into visual rows by their `top` (handles 1-2px sub-line jitter)."""
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


def _bucket(x1):
    """Return the 0..7 stat-column index for a number's right-edge, or None."""
    best, best_d = None, _ANCHOR_TOL
    for i, a in enumerate(_ANCHORS):
        d = abs(x1 - a)
        if d <= best_d:
            best, best_d = i, d
    return best


def parse_stock_open_rcpts_dualsales_pdf(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            for row_words in _cluster_rows(words):
                row_words = sorted(row_words, key=lambda w: w["x0"])
                joined = " ".join(w["text"] for w in row_words).strip()
                low = joined.lower()

                # header / rule / footer / page furniture
                if not joined:
                    continue
                if low.startswith("item name") or low.startswith("packg"):
                    continue
                if "grand total" in low or low.startswith("total"):
                    continue
                if (
                    "stock report" in low
                    or "page:" in low
                    or low.startswith("date")
                    or low.startswith("sai pharma")
                    or set(joined) <= set("- ")
                ):
                    continue

                cols = {}
                name_toks, pack_toks = [], []
                for w in row_words:
                    txt = w["text"]
                    if _is_num(txt) and w["x1"] >= _STAT_LEFT:
                        idx = _bucket(w["x1"])
                        if idx is not None:
                            cols[idx] = _to_f(txt)
                            continue
                    # not a stat number: name or pack region
                    if w["x0"] < _NAME_MAX_X0:
                        name_toks.append(txt)
                    elif w["x0"] < _PACK_MAX_X0:
                        pack_toks.append(txt)

                name = " ".join(name_toks).strip()
                if not name or not any(c.isalpha() for c in name):
                    continue
                if not cols:
                    continue

                open_stk = cols.get(0, 0.0)
                receipt = cols.get(1, 0.0)
                l_sales = cols.get(2, 0.0)
                cur_sls = cols.get(3, 0.0)
                pur_rtn = cols.get(4, 0.0)
                sls_rtn = cols.get(5, 0.0)
                clos_qty = cols.get(6, 0.0)
                clos_amt = cols.get(7, 0.0)

                # Pack: prefer a text pack in the packg region; a bare number there
                # (e.g. "250" -> 250ML truncated) is kept only if no text pack exists.
                pack = " ".join(t for t in pack_toks if not _is_num(t)).strip()
                if not pack:
                    pack = " ".join(pack_toks).strip()

                rec = {
                    "product_name": name,
                    "pack": pack,
                    "opening_stock": open_stk,
                    "purchase_stock": receipt,          # Receipts = purchases in
                    "sales_qty": cur_sls,                # Cur.Sls = current-period outflow
                    "purchase_return": pur_rtn,
                    "sales_return": sls_rtn,
                    "closing_stock": clos_qty,           # the QTY (2nd-to-last)
                    "closing_stock_value": clos_amt,     # the rupee VALUE (last)
                }
                if l_sales:
                    rec["prior_month_sales"] = l_sales   # L.Sales, informational only
                records.append(rec)
    return records
