import io
import re

import pdfplumber

# ---------------------------------------------------------------------------
# KLM "Group Vs Customer Details" — PRODUCT-BANDED customer sales dialect with
# Icode / Ipack / spldis columns (SRI SUBRAHMANYA PHARMACEUTICALS, ANAKAPALLI).
# Source: SRI SUBRAMAYA PHARMACEUTICALS/Party report/klm pd aer 30.5.pdf
#
# This is a DISTINCT format from the existing klm_group_vs_customer layout:
#   * that one is CUSTOMER-banded (customer "NAME (CODE)" is the band, item
#     inline) with columns Town|Date|Number|Batch|MRP|Qty|Free|Replace|Rate|
#     GrossValue|NetValue (gate token 'towndatenumberbatchmrpqtyfreereplace...').
#   * THIS one is PRODUCT-banded (item name on its own line, customers inline)
#     with columns ItemName|Icode|Ipack|Town|DocDate|BillNo|Batch|MRP|BQty|
#     BFree|Rate|NValue|NetValue|spldis|spldisamt.
#
# Exact column header (gate token, whitespace-stripped + lowercased):
#   ItemName Icode Ipack Town DocDate BillNo Batch MRP BQty BFree Rate NValue ...
#   -> "icodeipacktowndocdatebillnobatchmrpbqtybfreerate"
# Report title band: "Group Vs Customer Details From 01/May/26 To 31/May/26".
#
# Positional parse (word x-coordinates) is REQUIRED because the party name and
# the Icode column overlap in the flat text layer: the party name ends in
# "...STO" and Icode begins "KLMDS" at the SAME x (~170), so pdfplumber glues
# them into one token "STKOLMDS". Splitting on x-boundaries recovers both.
#
# Layout of one data row (left -> right, x0 of the header anchor):
#   ItemName(band, ~20) | Icode(~170) | Ipack(~212) | Town(~245) |
#   DocDate(~324) | BillNo="SP <num>"(~374) | Batch(~426) | MRP(~480) |
#   BQty(~524) | BFree(~555) | Rate(~601) | NValue(~633) | NetValue(~676) |
#   spldis spldisamt(~719).
#
# Field map (SACRED — qty and value never crossed):
#   product band  -> product_name
#   customer text -> party_name          (words in the ItemName column band on a data row)
#   Town          -> party_location
#   BillNo        -> invoice_number ("SP 1289")
#   DocDate       -> invoice_date
#   Batch         -> batch_no
#   MRP           -> mrp
#   BQty          -> qty       (sales_qty; the billed/paid quantity)
#   BFree         -> free_qty  (sales_free; scheme/free quantity)
#   Rate          -> rate
#   NValue        -> amount    (base value = BQty * Rate, self-checks on every row)
#   NetValue      -> net_amount
# Ipack -> Pack. Icode (the KLM internal item code) is used ONLY to find the
# item/party column edge that strips the overlap-glued icode glyphs off the
# party name; it is not emitted. Party sale report -> only the sales side exists.
#
# Reconcile: NValue == round(BQty * Rate, 2) on every priced row (verified 0
# fails on the source), and the printed page-footer total row (bare
# "173.00 21,825.79 23,424.00") equals sum(BQty)/sum(NValue)/sum(NetValue).
# ---------------------------------------------------------------------------

H = [
    "Party Name",
    "Location",
    "Product Name",
    "Pack",
    "Date",
    "Invoice Number",
    "Batch",
    "MRP",
    "Qty",
    "Free",
    "Rate",
    "Amount",
    "Net Amount",
]

_DATE = re.compile(r"\b\d{1,2}/[A-Za-z]{3}/\d{2,4}\b")
_MONEY = re.compile(r"^-?[\d,]+\.\d{1,2}$")
_NUMISH = re.compile(r"^-?[\d,]+(?:\.\d+)?$")

# Column x-boundaries (upper edge, exclusive) derived from the header anchors.
# A word is assigned to the FIRST column whose upper edge exceeds its x0.
_COLS = [
    ("item", 168.0),
    ("icode", 210.0),
    ("ipack", 243.0),
    ("town", 320.0),
    ("date", 370.0),
    ("bill", 424.0),
    ("batch", 472.0),
    ("mrp", 520.0),
    ("bqty", 552.0),
    ("bfree", 590.0),
    ("rate", 630.0),
    ("nvalue", 672.0),
    ("netvalue", 718.0),
    ("spl", 1e9),
]


def _fnum(tok):
    try:
        return float(str(tok).replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _fmt(x):
    return "%.2f" % x


# The icode column starts at x0 ~170.9. When a long party name's last letter
# lands at ~169 it VISUALLY overlaps the icode's first letter, so pdfplumber
# glues them into one word (e.g. "...GENERAKLMDS"). Splitting at char level on
# this edge recovers both the party tail and the icode cleanly.
_ITEM_ICODE_EDGE = 170.5


def _cluster(chars, tol=3.0):
    """Group chars into visual lines by 'top' (numbers on a data row can sit
    ~1px off the text baseline; a small tolerance merges them)."""
    cs = sorted(chars, key=lambda c: (c["top"], c["x0"]))
    lines, cur, ct = [], [], None
    for c in cs:
        if ct is None or abs(c["top"] - ct) <= tol:
            cur.append(c)
            if ct is None:
                ct = c["top"]
        else:
            lines.append(cur)
            cur, ct = [c], c["top"]
    if cur:
        lines.append(cur)
    return lines


def _line_text(line):
    """Reconstruct a visual line's text from its chars, inserting a space where
    a gap between consecutive glyphs exceeds ~half a char width."""
    out = []
    prev = None
    for c in sorted(line, key=lambda c: c["x0"]):
        if prev is not None and c["x0"] - prev > 1.6:
            out.append(" ")
        out.append(c["text"])
        prev = c["x1"]
    return "".join(out)


def _col_of(x0):
    for name, edge in _COLS:
        if x0 < edge:
            return name
    return "spl"


def _bucketize(line):
    """Assign each CHAR in a visual line to a column by its x0, then join. The
    char-level split lets an overlap-glued party/icode token be separated at the
    ~170.5 column edge."""
    buckets = {name: [] for name, _ in _COLS}
    for c in sorted(line, key=lambda c: c["x0"]):
        buckets[_col_of(c["x0"])].append(c)

    cols = {}
    for name, _ in _COLS:
        chunk = buckets[name]
        # rebuild with intra-column spacing
        out, prev = [], None
        for c in sorted(chunk, key=lambda c: c["x0"]):
            if prev is not None and c["x0"] - prev > 1.6:
                out.append(" ")
            out.append(c["text"])
            prev = c["x1"]
        cols[name] = "".join(out).strip()
    return cols


def _is_furniture(joined):
    up = re.sub(r"\s+", "", joined).lower()
    return (
        up.startswith("srisubrahmanya")
        or up.startswith("1stfloor")
        or up.startswith("groupvscustomer")
        or up.startswith("itemname")
    )


def parse_r15_klm_group_vs_customer_icode(text, file_bytes=None):
    rows = []
    if not file_bytes:
        return H, rows

    product = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            chars = page.chars
            if not chars:
                continue
            for line in _cluster(chars):
                s = _line_text(line).strip()
                if not s:
                    continue
                if _is_furniture(s):
                    continue

                has_date = bool(_DATE.search(s))

                # ---- product band: a text-only line with NO date, all words in
                #      the ItemName column, no money tokens ----------------------
                if not has_date:
                    money = [t for t in s.split() if _MONEY.match(t)]
                    if money:
                        # a bare page-footer total line (only numbers) -> skip
                        continue
                    if re.search(r"[A-Za-z]", s):
                        product = s.strip()
                    continue

                # ---- data row (date-anchored) ------------------------------
                # The item/icode column edge is what strips the overlap-glued
                # icode glyphs OFF the party name, leaving a clean party. The
                # Icode value itself (KLMDS/KLKD3...) is the KLM internal item
                # code and is NOT emitted (product identity is product_name).
                cols = _bucketize(line)
                party = re.sub(r"\s{2,}", " ", cols["item"].strip())
                ipack = cols["ipack"].strip()
                town = cols["town"].strip()
                date_tokens = [t for t in cols["date"].split() if _DATE.match(t)]
                date = date_tokens[0] if date_tokens else ""
                bill = cols["bill"].strip()
                batch = cols["batch"].strip()

                def _one(colname):
                    vals = [t for t in cols[colname].split() if _NUMISH.match(t)]
                    return vals[-1] if vals else ""

                mrp = _one("mrp")
                bqty = _one("bqty")
                bfree = _one("bfree")
                rate = _one("rate")
                nvalue = _one("nvalue")
                netvalue = _one("netvalue")

                if not party or not product:
                    continue
                # need at least the sales quantity/value pair to be a real row
                if bqty == "" and bfree == "":
                    continue

                rows.append([
                    party,
                    town,
                    product,
                    ipack,
                    date,
                    bill,
                    batch,
                    _fmt(_fnum(mrp)),
                    _fmt(_fnum(bqty)),
                    _fmt(_fnum(bfree)),
                    _fmt(_fnum(rate)),
                    _fmt(_fnum(nvalue)),
                    _fmt(_fnum(netvalue)),
                ])

    return H, rows
