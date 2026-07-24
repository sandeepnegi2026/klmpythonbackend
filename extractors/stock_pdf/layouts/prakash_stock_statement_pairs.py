"""PRAKASH MEDICAL AGENCY "STOCK STATMENT" (KLM ERP, spaced-letter glyph header).

One PDF per KLM division (e.g. KLM-DERMA). The report title reads:

    PRAKASH MEDICAL AGENCY
    30/05/2026 STOCK STATMENT DATED FROM :01/05/2026 TO 30/05/2026 Page No.1

and the column header is printed with SPACE-SEPARATED letters (a dot-matrix glyph
style), so pdfplumber reads it as individual glyphs:

    I T E M  N A M E   QTY. VALUE   P U R C H A S E   PURCHASE RETU.   S A L E S \
        SALES RETURN   CLOSING BALANCE

There are 6 (qty, value) PAIRS = 12 numbers per data row, right-aligned to fixed
x-positions (the "QTY. VALUE" heading of the first pair is the OPENING balance):

    x1 anchors  QTY  ~248  ~347  ~453  ~560  ~663  ~760
                VAL  ~301  ~404  ~506  ~619  ~716  ~821
    section    opening  purchase  purch.retu  sales  sales.return  closing

Every data row starts with a literal '#' marker, then the product+pack (a single
comma-joined token like  CANROLFIN,CREAM,30GM  or  ONITRAZ,CAP,1*10 ), then the 12
numbers. Because the pack digits (30GM, 1*10) glue into the name token they would
pollute a flat number-tail split, and long names WRAP to a second glyph-less line
(e.g.  NEVLON GLO SYNDET,SOAP,75 / GM  and  NEVLONMOISTURIZING / CREAM,SOAP,75GM ).
For both reasons this is parsed POSITIONALLY: name text = words left of the first
number band; numbers are bucketed to the nearest column anchor by right edge (x1).
A wrap line (glyph-less, no numbers, only left-band text) is appended to the pending
product name.

Column -> canonical mapping (first-of-pair = qty, second = value/rupees):
  opening      QTY -> opening_stock          VALUE -> opening_value
  purchase     QTY -> purchase_stock         VALUE -> purchase_value
  purch. retu  QTY -> purchase_return        VALUE -> (money, dropped)
  sales        QTY -> sales_qty              VALUE -> sales_value
  sales return QTY -> sales_return           VALUE -> (money, dropped)
  closing      QTY -> closing_stock          VALUE -> closing_stock_value

The generic parser mis-read this grid: it slid the OPENING *value* (money) into
purchase_stock and also into closing_stock. Mapping first-of-pair -> qty and
second-of-pair -> value fixes that.

Reconcile identity (postprocess.sanity_warnings):
  closing_stock == opening_stock + purchase_stock + purchase_free
                   - purchase_return - sales_qty - sales_free + sales_return
holds row-wise (every sample row is opening-only, e.g. CANROLFIN 4+0-0-0-0+0=4).
Group footer oracle for DERMA__klm derma may 26.pdf ("TOTAL OF :KLM-DERMA"):
  CLOSING BALANCE 66 qty / 10964.00 value ; PURCHASE 0/0 ; SALES 0/0.

Footer/band skips: the KLM division band ("KLM-DERMA") and the "TOTAL OF :..."
group-total block (which prints "P U R C H A S E 0 0.00" etc.) carry no '#' marker
and are ignored. The report-title / spaced-letter header rows likewise have no '#'.
"""
import io
import re
from collections import defaultdict

import pdfplumber

# Column anchors are the RIGHT edge (x1) of each printed number. Values measured on
# the DERMA sample; a +/-18pt tolerance to the nearest anchor absorbs digit-width
# jitter (2-digit vs 4-digit numbers shift the left edge, never the right edge).
# (key, x1_anchor). Order is opening, purchase, purch-return, sales, sales-return,
# closing -- each a (qty, value) pair.
_COL_ANCHORS = [
    ("opening_stock", 248.0),
    ("opening_value", 301.0),
    ("purchase_stock", 347.0),
    ("purchase_value", 404.0),
    ("purchase_return", 453.0),
    ("_purchase_return_value", 506.0),
    ("sales_qty", 560.0),
    ("sales_value", 619.0),
    ("sales_return", 663.0),
    ("_sales_return_value", 716.0),
    ("closing_stock", 760.0),
    ("closing_stock_value", 821.0),
]

# Left edge of the first number band. Anything with x0 below this is name/pack text.
_NUM_X0 = 190.0

_NUM_RE = re.compile(r"^-?[0-9][0-9,]*\.?[0-9]*$")

# Value keys that carry rupees (used only to decide float precision; not required).
_VALUE_KEYS = {
    "opening_value", "purchase_value", "_purchase_return_value",
    "sales_value", "_sales_return_value", "closing_stock_value",
}


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _extract_word_rows(file_bytes):
    """Yield [word,...] rows clustered by y-top (x-sorted), page after page."""
    out = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            by_top = {}
            for w in words:
                key = round(w["top"])
                matched = None
                for k in by_top:
                    if abs(k - key) <= 2:
                        matched = k
                        break
                by_top.setdefault(matched if matched is not None else key, []).append(w)
            for top in sorted(by_top):
                out.append(sorted(by_top[top], key=lambda w: w["x0"]))
    return out


def _bucket_numbers(nums):
    """Assign each numeric word to the nearest column anchor by right-edge x1."""
    out = {}
    for w in nums:
        key, _ = min(_COL_ANCHORS, key=lambda kv: abs(kv[1] - w["x1"]))
        # nearest wins; ties never occur (anchors are >=45pt apart)
        out[key] = _to_f(w["text"])
    return out


def parse_prakash_stock_statement_pairs(text, file_bytes=None):
    if not file_bytes:
        return []

    records = []
    pending = None  # the last emitted record, so a wrapped name line can append

    for row in _extract_word_rows(file_bytes):
        toks = [w["text"] for w in row]
        nums = [w for w in row if w["x0"] >= _NUM_X0 and _NUM_RE.match(w["text"])]

        if toks and toks[0] == "#":
            # A data row. Name/pack = the left-band words after the '#' marker.
            name_toks = [
                w["text"] for w in row
                if w["x0"] < _NUM_X0 and w["text"] != "#"
            ]
            name = " ".join(name_toks).strip()
            col = _bucket_numbers(nums)
            rec = {
                "product_name": name,
                "pack": "",
                "opening_stock": col.get("opening_stock", 0.0),
                "opening_value": col.get("opening_value", 0.0),
                "purchase_stock": col.get("purchase_stock", 0.0),
                "purchase_value": col.get("purchase_value", 0.0),
                "purchase_return": col.get("purchase_return", 0.0),
                "sales_qty": col.get("sales_qty", 0.0),
                "sales_value": col.get("sales_value", 0.0),
                "sales_return": col.get("sales_return", 0.0),
                "closing_stock": col.get("closing_stock", 0.0),
                "closing_stock_value": col.get("closing_stock_value", 0.0),
            }
            records.append(rec)
            pending = rec
            continue

        # Non-data row. If it is a glyph-less wrap continuation of the previous
        # product name (only left-band text, NO numbers, and not a footer/band
        # keyword), append it to the pending name.
        if pending is not None and not nums and toks:
            line = " ".join(toks).strip()
            low = line.lower()
            if (line and w0_is_name_wrap(row)
                    and not low.startswith(("total of", "closing balance",
                                            "p u r c h a s e", "purchase retu",
                                            "s a l e s", "sales return",
                                            "i t e m", "prakash", "stock statment",
                                            "klm-", "[#]"))):
                pending["product_name"] = (
                    pending["product_name"] + line
                    if pending["product_name"].endswith(",")
                    else pending["product_name"] + " " + line
                ).strip()
        # otherwise: title/header/band/footer -> ignore, and clear pending so a
        # later stray line cannot glue onto an old product.
        if toks and (toks[0] != "#") and nums:
            pending = None

    return records


def w0_is_name_wrap(row):
    """A wrap line is entirely in the left name band (x0 < _NUM_X0)."""
    return all(w["x0"] < _NUM_X0 for w in row)
