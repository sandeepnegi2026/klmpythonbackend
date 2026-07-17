"""KLM "Stock sales statement(Combined)" - pipe-delimited FLAT-TEXT render (SAMBARI ENTERPRISES).

Distinct from klm_stock_sales_combined_pdf (VISION HEALTHCARE HOLDINGS): that variant
renders the same logical report as a wrapped .xlsx grid where header words are separate
positioned tokens and long values wrap their low-order digits onto the next visual line,
so it needs a word-x-position (positional) parser. THIS SAMBARI render is a clean
single-line-per-product ``|``-delimited flat text dump - every product is exactly one
line and every column is a pipe cell, so a simple pipe-split reads it losslessly. On this
file the positional parser's _find_anchors fails (the header is glued into pipe tokens
``Rate|Prev.Sale|`` / ``Opening|Purchase|Total`` rather than standalone ``Rate`` / ``Openi``
/ ``Purch`` words) and it returns 0 rows.

Gate token (spaces-stripped, lowercased contiguous header run, unique to this render):
    ``|rate|prev.sale|opening|purchase|totalsale|salevalue|adj.|totalclosing|closingvalue``

Header (11 pipe cells):
    Product Name | Pack | Rate | Prev.Sale | Opening | Purchase | Total Sale |
    Sale Value | Adj. | Total Closing | Closing Value

Column -> canonical mapping (qty and value kept strictly separate):
    Opening       -> opening_stock
    Purchase      -> purchase_stock
    Total Sale    -> sales_qty         (a QTY column, NOT the Sale Value rupee column)
    Sale Value    -> sales_value
    Total Closing -> closing_stock
    Closing Value -> closing_stock_value
    Adj.          -> signed adjustment. Movement identity in the source is
                     Opening + Purchase - Total Sale + Adj = Total Closing
                     (verified: ZYDIP-C 25+20-12-5=28; IMXIA-5 18-1-2=15;
                      KOFCATCH-LD 21-21=0; SACCTIK PLUS 90+400-40-10=440).
                     Reconcile slots: a NEGATIVE Adj is a purchase_return (subtract),
                     a POSITIVE Adj is a sales_return (add). Prev.Sale is informational
                     and is DELIBERATELY not mapped.

Skipped: division band rows (``KLM LABORATORIES PVT LTD(...DIV)``), the per-division
``Total Value`` / final ``Total`` footer rows, ``Bill Nos.`` / ``AMP/...`` / ``Dt....``
lines, ``Printed on`` / ``End of report`` / ``Page`` banners, dashed rules, and any row
whose product cell is empty or numeric.
"""
import re

from ..parse_common import _to_number

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")

_SKIP_RE = re.compile(
    r"^(total value|total|bill nos|amp/|dt\.|page\b|printed on|end of report|"
    r"stock sales statement|product name)",
    re.I,
)
# Division band: "KLM LABORATORIES PVT LTD(COSMO-1 DIV)" etc.
_BAND_RE = re.compile(r"laboratories\s+pvt\s+ltd", re.I)


def _cell(v):
    return (v or "").strip()


def _num(v):
    n = _to_number(_cell(v))
    return 0.0 if n is None else n


def parse_klm_ss_combined_pipe_flat(text):
    if not text:
        return []
    records = []
    for raw in text.splitlines():
        if "|" not in raw:
            continue
        cells = raw.split("|")
        if len(cells) < 11:
            continue
        name = _cell(cells[0])
        low = name.lower()
        if not name:
            continue
        if _SKIP_RE.match(low) or _BAND_RE.search(low):
            continue
        # numeric-only product cell -> not a product line
        stripped = name.replace(".", "", 1).replace(",", "").replace("-", "")
        if stripped.isdigit():
            continue

        pack = _cell(cells[1])
        rate = _num(cells[2])
        # cells[3] = Prev.Sale (informational, intentionally unmapped)
        opening = _num(cells[4])
        purchase = _num(cells[5])
        sales_qty = _num(cells[6])
        sales_value = _num(cells[7])
        adj = _num(cells[8])
        closing = _num(cells[9])
        closing_value = _num(cells[10]) if len(cells) > 10 else 0.0

        rec = {
            "product_name": re.sub(r"\s+", " ", name),
            "pack": pack,
            "rate": rate,
            "opening_stock": opening,
            "purchase_stock": purchase,
            "sales_qty": sales_qty,
            "sales_value": sales_value,
            "closing_stock": closing,
            "closing_stock_value": closing_value,
        }
        # Signed adjustment -> return slots so the reconcile identity holds:
        # opening + purchase + purchase_free - purchase_return
        #   - sales_qty - sales_free + sales_return = closing
        if adj < 0:
            rec["purchase_return"] = -adj      # subtractive
        elif adj > 0:
            rec["sales_return"] = adj          # additive

        # drop wholly empty product rows (rate only 0 and no movement at all)
        if all(rec.get(f, 0.0) == 0.0 for f in
               ("rate", "opening_stock", "purchase_stock", "sales_qty", "closing_stock")):
            continue
        records.append(rec)
    return records
