import re

# ---------------------------------------------------------------------------
# "PARTYWISE/ITEMWISE SALE" — party-banded item-wise sale report with a
# PACKING column folded into the item name and a QUANTITY / FREE / TOT.QTY. /
# VALUE numeric tail (RAMESH MEDICAL STORES, Ujjain; KLM distributor).
# Source file: RAMESH MEDICAL/Party report/KLMP.PDF
#
# Exact column header (gate token, whitespace-stripped + lowercased):
#     <-----ITEM NAME-------> PACKING QUANTITY FREE TOT.QTY. VALUE
#     -> ...packingquantityfreetot.qty.value
# Report title: "PARTYWISE/ITEMWISE SALE".
#
# Page/report furniture repeats on every page:
#     Ramesh Medical Stores,UJJAIN                     <- vendor banner
#     9,Medicine Lane, ... ,indore                     <- address
#     PARTYWISE/ITEMWISE SALE                           <- report title
#     From 01/05/2026 To 31/05/2026 Page : 1           <- period + page
#     <-----ITEM NAME-------> PACKING QUANTITY FREE TOT.QTY. VALUE   <- header
#
# Body nesting (one block per party):
#     3 F PHARMACY,UJJAIN                               <- PARTY,TOWN band
#     COSMOQ AC GEL SPF-30 60GM 2.00 2.00 729.96        <- item row
#     ...
#     PARTY TOTAL : 729.96                              <- per-party subtotal (skip)
#     ...
#     TOTAL VALUE :                                     <- report total (skip)
#
# The "PACKING" header column is NEVER a standalone numeric token — the pack
# strength ("60GM", "1*10 STRIP", "20'S", "1*3TAB") is glued inside the item
# name. So a product row carries EITHER 3 or 4 trailing numbers:
#
#   3 numbers -> QUANTITY  TOT.QTY.  VALUE      (FREE column omitted => free 0)
#                COSMOQ AC GEL SPF-30 60GM 2.00 2.00 729.96
#                QUANTITY == TOT.QTY. on every such row (self-check, 0 fails).
#   4 numbers -> QUANTITY  FREE  TOT.QTY.  VALUE
#                ONITRAZ CAP 1*10 STRIP 20.00 2.00 22.00 2560.80
#                TOT.QTY. == QUANTITY + FREE on every such row (0 fails).
#
# A couple of rows carry NO value (VALUE column blank), leaving only 2 trailing
# numbers (QUANTITY TOT.QTY.); those are emitted with amount "" .
#
# Field map (SACRED — qty and value never mixed):
#   PARTY,TOWN band  -> party_name / party_location (split on last comma)
#   item text        -> product_name (pack strength stays glued, as printed)
#   QUANTITY         -> qty      (sales_qty; the PAID quantity)
#   FREE             -> free_qty (sales_free; 0 when the column is absent)
#   VALUE            -> amount   (sole money column)
# TOT.QTY. is redundant (= QUANTITY + FREE) and is NOT emitted, so no value
# column is ever mapped onto a quantity slot. Party sale report -> only the
# sales side exists; it reconciles on QTY (= TOT.QTY.) and VALUE against the
# printed per-party 'PARTY TOTAL :' lines.
# ---------------------------------------------------------------------------

_NUM = r"-?\d[\d,]*(?:\.\d+)?"

# item row: <name> + 2, 3 or 4 trailing numeric columns.
#   4-num: qty free totqty value
#   3-num: qty totqty value        (free absent)
#   2-num: qty totqty              (value blank)
_ROW4 = re.compile(
    rf"^(?P<name>.*?\S)\s+(?P<qty>{_NUM})\s+(?P<free>{_NUM})\s+"
    rf"(?P<totqty>{_NUM})\s+(?P<value>{_NUM})\s*$"
)
_ROW3 = re.compile(
    rf"^(?P<name>.*?\S)\s+(?P<qty>{_NUM})\s+(?P<totqty>{_NUM})\s+"
    rf"(?P<value>{_NUM})\s*$"
)
_ROW2 = re.compile(
    rf"^(?P<name>.*?\S)\s+(?P<qty>{_NUM})\s+(?P<totqty>{_NUM})\s*$"
)

# report / page furniture to drop (compact, lowercased predicate).
_SKIP_COMPACT = (
    "partywise/itemwise",          # report title
    "packingquantityfreetot",      # column header run
)


def _f(tok):
    return tok.replace(",", "")


def _num_eq(a, b):
    try:
        return abs(float(a) - float(b)) < 0.01
    except ValueError:
        return False


def _split_party_town(raw):
    """Split '<PARTY NAME>,<TOWN>' into (name, town) on the LAST comma.
    Names without a comma keep the whole text and an empty town."""
    s = raw.strip()
    if "," in s:
        name, town = s.rsplit(",", 1)
        return name.strip(), town.strip()
    return s, ""


def parse_r15_ramesh_partywise_itemwise_pack(text):
    H = ["Party Name", "Location", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    party_name = party_town = ""

    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            continue
        compact = re.sub(r"\s+", "", s.lower())

        # per-party subtotal / report total -> skip
        if compact.startswith("partytotal") or compact.startswith("totalvalue"):
            continue
        # page furniture: title, column header, address, period+page, banner.
        if any(tok in compact for tok in _SKIP_COMPACT):
            continue
        if compact.startswith("from") and "page:" in compact:
            continue
        # vendor banner + address (both contain a comma but end in text, not a
        # number) are handled by the item-row test below failing and the band
        # test only firing for the FIRST party after the header. The banner/
        # address recur verbatim; drop them explicitly.
        if compact.startswith("rameshmedicalstores"):
            continue
        if re.match(r"^\d+,medicinelane", compact):
            continue

        # ---- item row (4 / 3 / 2 trailing numbers) --------------------------
        m4 = _ROW4.match(s)
        if m4 and party_name:
            name = m4.group("name").strip()
            qty = _f(m4.group("qty"))
            free = _f(m4.group("free"))
            totqty = _f(m4.group("totqty"))
            # true 4-column row only when totqty == qty + free
            try:
                if abs((float(qty) + float(free)) - float(totqty)) < 0.01:
                    rows.append([party_name, party_town, name, qty, free,
                                 _f(m4.group("value"))])
                    continue
            except ValueError:
                pass

        m3 = _ROW3.match(s)
        if m3 and party_name:
            name = m3.group("name").strip()
            qty = _f(m3.group("qty"))
            totqty = _f(m3.group("totqty"))
            # 3-num rows: FREE column absent, so qty == totqty
            if _num_eq(qty, totqty):
                rows.append([party_name, party_town, name, qty, "0",
                             _f(m3.group("value"))])
                continue

        m2 = _ROW2.match(s)
        if m2 and party_name:
            name = m2.group("name").strip()
            qty = _f(m2.group("qty"))
            totqty = _f(m2.group("totqty"))
            if _num_eq(qty, totqty):
                rows.append([party_name, party_town, name, qty, "0", ""])
                continue

        # ---- otherwise a PARTY,TOWN band heading ----------------------------
        # A band has letters and no trailing numeric run (already excluded above).
        if re.search(r"[A-Za-z]", s):
            party_name, party_town = _split_party_town(s)

    return H, rows
