"""KLM "Stock and Sale Statement" — VENUS PHARMA export (KLM MAY.XLSX), division-banded.

Sheet shape (title/address rows on top, then one wide grid banded by division)::

    VENUS PHARMA                                                         <- title (cols 3..16)
    PLOT NO C 11/3/A ... Ph:...                                          <- address
    Stock and Sale Statement  From  01-May-26 to 31-May-26              <- period
    (col6) Item | Mar 26 | Apr 26 | OpStk | P.Qty | P.Val | P.Sch |     <- header (col6..21)
           S.Qty | S.Sch | S.Val | CrQty | CrQty | CrSchQty | ClStk | ClVal | Order
    (col6) KLM LABORATORIES -COSMOCOR                                    <- division band (col6 only)
    XA0001 | (col3 division) | XA0162 | EPISERT CREAM 30GM | ...         <- data row
    ...
    (footer) 518 | 669 | 967 | ...                                      <- per-division subtotal (no col6)

Column layout (0-based physical indices, from the header row that has "Item" in col6):
  col3  = DIVISION band text, repeated on EVERY data row (e.g. "KLM LABORATORIES -COSMOCOR")
  col5  = item code (present only on real product rows)
  col6  = Item / product name
  col7  = Mar 26 (prior-period sale history — informational, NOT mapped)
  col8  = Apr 26 (prior-period sale history — informational, NOT mapped)
  col9  = OpStk   -> opening_stock
  col10 = P.Qty   -> purchase_stock
  col11 = P.Val   (purchase value — not required)
  col12 = P.Sch   -> purchase_free   (scheme / free purchase qty)
  col13 = S.Qty   -> sales_qty
  col14 = S.Sch   -> sales_free
  col15 = S.Val   -> sales_value
  col16/17 = CrQty (duplicate current/credit qty analytics — NOT mapped)
  col18 = CrSchQty (not mapped)
  col19 = ClStk   -> closing_stock
  col20 = ClVal   -> closing_value
  col21 = Order   (pending order — not mapped)

Why a dedicated POSITIONAL parser (like ``prompt_dstk_free_xlsx`` / ``klm_dstk_stock``)
rather than the generic ``tabular`` matcher:

* The prior-month sale-history columns ``Mar 26`` / ``Apr 26`` sit immediately before OpStk
  and fuzzy-collide with the sales synonyms, and the duplicated ``CrQty`` analytics columns
  have no canonical home, so the generic index-mapper mis-routes the movement columns and
  every row fails the sanity equation.
* The product name (col6) is offset from the row's serial (col1) and item code (col5), and
  the division lives in a separate band column (col3), which the generic reader has no
  concept of.

Reconciles exactly (blank cell -> 0):
  closing(ClStk) = opening(OpStk) + purchase(P.Qty) + purchase_free(P.Sch)
                                  - sales(S.Qty) - sales_free(S.Sch)
e.g. MELBOOST SOLUTION 5ML: 19 == 4 + 1 + 14 - 0 - 0  (EXACT)
     EPISERT CREAM 30GM:    76 == 76 + 0 + 0 - 0 - 0   (EXACT)
"""
from extractors.stock_xlsx.parse_common import cell_text

# Physical column index -> canonical field (fixed layout, keyed off the "Item"-in-col6 header).
_COL = {
    9: "opening_stock",
    10: "purchase_stock",
    12: "purchase_free",
    13: "sales_qty",
    14: "sales_free",
    15: "sales_value",
    19: "closing_stock",
    20: "closing_stock_value",
}
_DIVISION_COL = 3
_CODE_COL = 5
_NAME_COL = 6


def _num(cell):
    s = cell_text(cell).strip()
    if s in ("", "-"):
        return 0.0
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _find_header(rows):
    """Header row = the one carrying 'Item' in col6 plus OpStk/P.Qty/S.Qty/ClStk across."""
    for idx, row in enumerate(rows[:20]):
        labels = [cell_text(c).strip().lower() for c in row]
        joined = " ".join(labels)
        if (
            _NAME_COL < len(labels)
            and labels[_NAME_COL] == "item"
            and "opstk" in joined
            and "p.qty" in joined
            and "s.qty" in joined
            and "clstk" in joined
        ):
            return idx
    return None


def parse_klm_venus_opstk_crqty(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}

    records = []
    for raw in rows[header_idx + 1:]:
        product = cell_text(raw[_NAME_COL]) if _NAME_COL < len(raw) else ""
        code = cell_text(raw[_CODE_COL]) if _CODE_COL < len(raw) else ""
        # A real product row carries BOTH an item code (col5) and a name (col6). Division
        # band-only rows have col6 set but col5 empty; footer/subtotal rows have col6 empty.
        if not product or not code:
            continue
        if product.strip().lower() == "item":
            continue

        record = {"product_name": product}
        division = cell_text(raw[_DIVISION_COL]) if _DIVISION_COL < len(raw) else ""
        if division:
            record["division"] = division

        skip = False
        for idx, key in _COL.items():
            v = _num(raw[idx]) if idx < len(raw) else 0.0
            if v is None:            # a stray non-numeric cell -> not a real data row
                skip = True
                break
            record[key] = str(int(v)) if v == int(v) else str(v)
        if skip:
            continue
        records.append(record)

    detected = {
        "Item": "product_name",
        "(band col3)": "division",
        "OpStk": "opening_stock",
        "P.Qty": "purchase_stock",
        "P.Sch": "purchase_free",
        "S.Qty": "sales_qty",
        "S.Sch": "sales_free",
        "S.Val": "sales_value",
        "ClStk": "closing_stock",
        "ClVal": "closing_stock_value",
    }
    return records, detected
