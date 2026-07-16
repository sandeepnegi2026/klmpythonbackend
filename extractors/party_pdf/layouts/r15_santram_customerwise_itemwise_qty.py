import re

# ---------------------------------------------------------------------------
# "Customerwise Itemwise Qty Sales" — party-banded item-wise sale report from a
# KLM distributor (SANTRAM PHARMA PRIVATE LIMITED, Vadodara). One block per
# customer; each item line carries a Marketed-By ("KLM"), a Division band, an
# item code, the item name (with the Packing column glued after it) and a
# QTY / FQTY / VALUE numeric tail.
# Source file: SANTRAM PHARMA .../Party report/KLM PARTYWISE.pdf
#
# Exact column header (gate token, whitespace-stripped + lowercased). NOTE the
# "." after "Sr" survives the whitespace-only compaction:
#     Sr. Mkt By Division Code Item Name Packing Qty FQty Value
#     -> sr.mktbydivisioncodeitemnamepackingqtyfqtyvalue
# Report title: "Customerwise Itemwise Qty Sales for the period of ...".
#
# Page / report furniture repeats on every page:
#     SANTRAM PHARMA PRIVATE LIMITED                         <- vendor banner
#     PATEL PEN LANE, SHIYAPURA, RAOPURA                     <- address
#     RAOPURA, VADODARA - 390001, GUJARAT - 24               <- address
#     Contact: ... Mobile: ... Email: ...                    <- contact
#     Year : 2026-27 Page 1 of 12                            <- year + page
#     Customerwise Itemwise Qty Sales for the period ...     <- report title
#     Sr. Mkt By Division Code Item Name Packing Qty FQty Value  <- column header
#     Location : VADODARA                                    <- location band
#     ADMIN (17/06/2026 4:20:12 PM)                          <- footer stamp
#
# Body nesting (one block per party):
#     80 - A ROY AND CO, RAOPURA VADODARA                    <- <CODE> - <PARTY>, <AREA> <CITY>
#     1 KLM PEDIA 9355 SOFIBAR SYNDET BAR 75GM 5 0 660.15    <- item row
#     ...
#     Total of A ROY AND CO : 15 - 2665.75                   <- per-party subtotal (skip)
#     Total of VADODARA Location : 973 76 213721.59          <- location total (skip)
#     Grand Total : 973 76 213721.59                         <- report total (skip)
#
# Item row layout:
#     <Sr> KLM <DIVISION> <CODE> <ITEM NAME + PACKING> <QTY> <FQTY> <VALUE>
#   - "Mkt By" is always the literal "KLM".
#   - <DIVISION> is a single UPPERCASE token (PEDIA, DERMA, DERMACORE, COSME,
#     COSMOCORE, COSMOQ, PHARMA).
#   - <CODE> is an item code (numeric like 9355 or alphanumeric like SEBO0001);
#     it is dropped from the product name.
#   - The Packing column is glued at the end of the item name (as printed).
#   - Trailing numbers: QTY (integer), FQTY (integer, the FREE quantity),
#     VALUE (money, has a decimal point).
#
# Field map (SACRED — qty and value never mixed):
#   <CODE> - <PARTY>, <AREA> <CITY> band -> party_name / party_location
#   ITEM NAME (+ packing)                -> product_name
#   QTY                                  -> qty      (sales_qty; the PAID qty)
#   FQTY                                 -> free_qty (sales_free)
#   VALUE                                -> amount   (sole money column)
# Party sale report -> only the sales side exists; it reconciles on QTY
# (sum=973) + FREE (sum=76) + VALUE (sum=213721.59) against 'Grand Total :'.
# ---------------------------------------------------------------------------

_DIVISIONS = {
    "PEDIA", "DERMA", "DERMACORE", "COSME", "COSMOCORE", "COSMOQ", "PHARMA",
}

# item row: "<sr> KLM <DIVISION> <rest...> <qty> <fqty> <value>"
#   qty / fqty are bare integers; value carries a decimal point.
_ROW = re.compile(
    r"^\d+\s+KLM\s+(?P<div>[A-Z]+)\s+(?P<rest>.+?)\s+"
    r"(?P<qty>\d[\d,]*)\s+(?P<free>\d[\d,]*)\s+(?P<value>\d[\d,]*\.\d+)\s*$"
)

# party band: "<CODE> - <PARTY NAME>, <AREA> <CITY>"
_BAND = re.compile(r"^(?P<code>[A-Za-z0-9]+)\s+-\s+(?P<rest>.+)$")

# leading item-code token to strip off the front of <rest> (numeric like 9355
# or alphanumeric like SEBO0001 / COSM0004 / K DO0001).
_CODE_LEAD = re.compile(r"^(?:[A-Z]{1,3}\s)?[A-Za-z0-9]+\s+")

_SKIP_COMPACT = (
    "customerwiseitemwiseqty",       # report title run
    "srmktbydivisioncode",           # column-header run
    "santrampharmaprivate",          # vendor banner
)


def _f(tok):
    return tok.replace(",", "")


def _split_party_location(raw):
    """'<PARTY NAME>, <AREA> <CITY>' -> (name, location) on the LAST comma."""
    s = raw.strip()
    if "," in s:
        name, loc = s.rsplit(",", 1)
        return name.strip(), loc.strip()
    return s, ""


def parse_r15_santram_customerwise_itemwise_qty(text):
    H = ["Party Name", "Location", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    party_name = party_loc = ""

    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            continue
        compact = re.sub(r"\s+", "", s.lower())

        # per-party / location / grand totals -> skip
        if compact.startswith("totalof") or compact.startswith("grandtotal"):
            continue
        # page furniture: title, column header, vendor banner
        if any(tok in compact for tok in _SKIP_COMPACT):
            continue
        # year+page / contact / location band / admin footer
        if compact.startswith("year:") or compact.startswith("contact:"):
            continue
        if compact.startswith("location:") or compact.startswith("admin("):
            continue

        # ---- item row (qty fqty value tail, div gated) ----------------------
        m = _ROW.match(s)
        if m and m.group("div") in _DIVISIONS and party_name:
            rest = m.group("rest").strip()
            # drop the leading item-code token to isolate the item name
            name = _CODE_LEAD.sub("", rest, count=1).strip() or rest
            rows.append([
                party_name, party_loc, name,
                _f(m.group("qty")), _f(m.group("free")), _f(m.group("value")),
            ])
            continue

        # ---- party band "<CODE> - <PARTY>, <AREA> <CITY>" -------------------
        b = _BAND.match(s)
        if b and re.search(r"[A-Za-z]", b.group("rest")):
            party_name, party_loc = _split_party_location(b.group("rest"))

    return H, rows
