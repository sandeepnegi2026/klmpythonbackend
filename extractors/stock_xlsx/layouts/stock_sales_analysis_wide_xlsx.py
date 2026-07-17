"""KLM "STOCK & SALES ANALYSIS" WIDE stock-movement text dump (KRISHNA PHARMA).

The same KLM "STOCK & SALES ANALYSIS" report as ``stock_sales_analysis_oic_xlsx`` but with the
FULL movement grid instead of the reduced Opening/Receipt/Issue/Closing form. It is exported as
a plain fixed-width TEXT report pasted into column A of an .xls, so every row is one nbsp-padded
single cell (``load_data_sheets`` yields single-column rows). Two-row header::

    ITEM DESCRIPTION            OPENING            SALE   REPL./   TOTAL           PURCHASE   REPL./  CLOSING   RE-
                                STOCK   PURCHASES  RETURN OTHERS   STOCK   SALES   RETURN     OTHERS  STOCK     ORDER  M.EXP

so each data line is::

    <product> <pack> PCS  OPENING PURCHASES SALE-RETURN OTHERS(in) TOTAL SALES PURCH-RETURN OTHERS(out) CLOSING RE-ORDER  [M.EXP]

i.e. TEN numeric-or-nil movement columns after the "PCS" unit, then an optional "M.EXP"
(nearest-expiry mm/yy). Column map (0-based within the 10-number block):

    0 OPENING STOCK   -> opening_stock
    1 PURCHASES       -> purchase_stock
    2 SALE RETURN     -> sales_return   (inflow)
    3 REPL./OTHERS in -> folded into sales_return    (adds stock)
    4 TOTAL STOCK     -> total_stock    (= opening + all inflows; informational)
    5 SALES           -> sales_qty
    6 PURCHASE RETURN -> purchase_return (outflow)
    7 REPL./OTHERS out-> folded into purchase_return (removes stock)
    8 CLOSING STOCK   -> closing_stock
    9 RE-ORDER        -> order_qty      (analytics, outside the sanity equation)

With that folding ``closing = opening + purchases + sale_return - sales - purchase_return``
reconciles exactly on every row, and the printed "Quantity" control totals match
(opening 300 / sales 18 / closing 282).

Parsed positionally off the trailing 10 numbers so the free-width product/pack text is never
mis-split: peel M.EXP, take the last ten numeric-or-nil tokens as the movement block, then peel
the "PCS" unit and a trailing pack token to leave a clean product name. Division bands (a bare
"KLM" title line) carry no movement numbers and are dropped; the "Quantity" / "Value in Rs."
footer subtotals are skipped by keyword.
"""
import re

from extractors.stock_xlsx.constants import SUBTOTAL_RE

_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_NIL_RE = re.compile(r"^-+$")
_MEXP_RE = re.compile(r"^\d{1,2}/\d{2,4}$")
_UNITS = {"PCS", "PCTS", "PC", "NOS", "BOT", "BTL", "STRP", "STR"}
# A trailing pack token: bare count / "N*M" / "N-M" / "NX M" strip, or a unit-suffixed size
# ("200ML", "10GM", "1X10", "1*").
_PACK_RE = re.compile(r"^(?:\d+(?:[*xX\-]\d*)?|\d+[A-Za-z]+)$")
_NCOLS = 10

_OPEN, _PUR, _SRET, _OTH_IN = 0, 1, 2, 3
_TOTAL, _SALES, _PRET, _OTH_OUT = 4, 5, 6, 7
_CLOSE, _REORDER = 8, 9


def _num_or_nil(tok):
    if _NIL_RE.match(tok):
        return "0"
    return tok if _NUM_RE.match(tok) else None


def _as_int_str(value):
    return str(int(value)) if value == int(value) else str(value)


def parse_stock_sales_analysis_wide_xlsx(rows):
    records = []
    header_seen = False
    for row in rows:
        text = " ".join(str(c) for c in row).replace("\xa0", " ") if row else ""
        stripped = re.sub(r" +", " ", text).strip()
        if not stripped or set(stripped) <= set("-= "):
            continue
        low = stripped.lower()
        if "item description" in low and "opening" in low:
            header_seen = True
            continue
        if not header_seen:
            continue
        # Second header row: "STOCK PURCHASES RETURN OTHERS ... ORDER M.EXP" — the sub-labels.
        if low.startswith("stock") and "purchases" in low and "others" in low:
            continue
        if (
            SUBTOTAL_RE.match(stripped)
            or low.startswith("value in rs")
            or low.startswith("quantity")
        ):
            continue

        toks = stripped.split()
        expiry = toks.pop() if toks and _MEXP_RE.match(toks[-1]) else ""

        movement = []
        rest = toks[:]
        while rest and len(movement) < _NCOLS and (
            _NUM_RE.match(rest[-1]) or _NIL_RE.match(rest[-1])
        ):
            movement.append(rest.pop())
        movement.reverse()
        if len(movement) < _NCOLS or not rest:
            continue  # a division band title ("KLM") — no movement numbers

        if rest and rest[-1].upper() in _UNITS:
            rest.pop()  # drop the "PCS" unit column
        pack = ""
        if len(rest) >= 2 and _PACK_RE.match(rest[-1]):
            pack = rest.pop()
        product = " ".join(rest).strip()
        if not product:
            continue

        sales_return = float(_num_or_nil(movement[_SRET]) or 0) + float(
            _num_or_nil(movement[_OTH_IN]) or 0
        )
        purchase_return = float(_num_or_nil(movement[_PRET]) or 0) + float(
            _num_or_nil(movement[_OTH_OUT]) or 0
        )

        record = {
            "product_name": product,
            "opening_stock": _num_or_nil(movement[_OPEN]) or "0",
            "purchase_stock": _num_or_nil(movement[_PUR]) or "0",
            "sales_return": _as_int_str(sales_return),
            "total_stock": _num_or_nil(movement[_TOTAL]) or "0",
            "sales_qty": _num_or_nil(movement[_SALES]) or "0",
            "purchase_return": _as_int_str(purchase_return),
            "closing_stock": _num_or_nil(movement[_CLOSE]) or "0",
        }
        reorder = _num_or_nil(movement[_REORDER])
        if reorder not in (None, "0"):
            record["order_qty"] = reorder
        if pack:
            record["pack"] = pack
        if expiry:
            record["expiry"] = expiry
        records.append(record)

    detected = {
        "ITEM DESCRIPTION": "product_name",
        "OPENING STOCK": "opening_stock",
        "PURCHASES": "purchase_stock",
        "SALE RETURN + OTHERS (folded)": "sales_return",
        "TOTAL STOCK": "total_stock",
        "SALES": "sales_qty",
        "PURCHASE RETURN + OTHERS (folded)": "purchase_return",
        "CLOSING STOCK": "closing_stock",
    }
    return records, detected
