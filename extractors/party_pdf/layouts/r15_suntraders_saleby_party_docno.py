import re

# ---------------------------------------------------------------------------
# "List of Sale By Party" — Data Spec (www.dsgst.in) party-banded item-wise
# sale register (SUN TRADER / Bilaspur; KLM Laboratories distributor).
# Source file: SUN TRADERS/Party report/List of Sale By Item_260704.pdf
#
# Exact column header (gate token, whitespace-stripped + lowercased):
#     Sr. Date DocNo Item Name Qty Free MRP Pu Rate Rate Value Net Rate Amount
#     -> ...qtyfreemrppurateratevaluenetrateamount
# Report title: "List of Sale By Party" (footer: Data Spec www.dsgst.in).
#
# Page/report furniture repeats on every page:
#     SUN TRADER                                          <- vendor banner
#     GSTIn:22ACXPV7008C1ZF                               <- gstin
#     Shop 1,Medical Complex,Telipara Bilaspur ...        <- address
#     Page 1                                              <- page marker
#     List of Sale By Party                               <- report title
#     Mfr:Klm Laboratories Pvt. Ltd..                     <- manufacturer filter
#     Date From 01-06-2026 to 30-06-2026                  <- period
#     Sr. Date DocNo Item Name Qty Free MRP ...           <- column header
#     S/w support: Data Spec (www.dsgst.in) Report: ...   <- footer
#
# Body nesting (one block per party):
#     1 24X7 MEDICAL SHOP (Manglaa Chowk) BILASPUR        <- PARTY band  "<Sr> <name>"
#     1.1 02-06- 2627-CR-12535 Cetalore 10mg Tab {10`s} 10 103.13i 70.72 78.58 754.37 79.21 792.09
#     ...                                                 <- item rows "<Sr>.<n> ..."
#     2026                                                <- wrapped date tail (noise, dropped)
#     Total: of 24X7 MEDICAL SHOP 81 10,560.42 11,227.78  <- per-party subtotal (skip)
#     Grand Total: 876 26 1,44,734.66 1,54,432.06          <- report total (skip)
#
# Item row numeric tail (SACRED — qty and value never mixed):
#     <Sr>.<n> <DD-MM-> <DocNo> <Item Name...> <TAIL>
#   where TAIL is, per the column header, one of:
#     8 nums: Qty Free MRP PuRate Rate Value NetRate Amount   (FREE present)
#     7 nums: Qty      MRP PuRate Rate Value NetRate Amount   (FREE column blank)
#   The FREE column is printed only on rows that actually carry free goods
#   (e.g. "2.1 ... Mupisoft Oint {5gm} 40 16 108.33 ...": Qty=40 Free=16), so
#   the count of trailing numbers alone (7 vs 8) discriminates the two shapes.
#   MRP occasionally carries a glued 'i' flag ("103.13i"); the number regex
#   allows a single trailing letter which is stripped before we discard it.
#
# Field map:
#   PARTY band ("<Sr> <name>")  -> party_name (last CAPS/paren town kept inline)
#   Item Name  (pack in braces) -> product_name (as printed)
#   Qty                          -> qty      (sales_qty; PAID quantity)
#   Free                         -> free_qty (sales_free; 0 when column blank)
#   Amount                       -> amount   (net money; Grand Total 1,54,432.06
#                                             == SUM(Amount), self-verified)
# MRP / PuRate / Rate / Value / NetRate are per-unit / taxable-base columns and
# are NOT emitted — no value/amount column is ever mapped onto a quantity slot.
# Party sale report -> only the sales side exists; reconcile is on QTY and on
# the AMOUNT column against the printed "Total: of <party>" / "Grand Total:"
# lines.
# ---------------------------------------------------------------------------

# a numeric token: 1,44,734.66  103.13  10  103.13i  (single trailing flag letter)
_NUM = r"-?[\d,]+(?:\.\d+)?[a-zA-Z]?"

# item row: "<Sr>.<n> <date> <docno> <name...> <7 or 8 trailing numbers>"
_ITEM = re.compile(
    r"^\d+\.\d+\s+\d{2}-\d{2}-\s+\S+\s+(?P<rest>.+)$"
)
# PARTY band: "<Sr> <name...>" (single integer serial, then text, NO trailing
# numeric-column run).
_BAND = re.compile(r"^\d+\s+(?P<name>\S.*)$")

_TAIL7 = re.compile(
    rf"^(?P<name>.*?\S)\s+(?P<qty>{_NUM})\s+(?P<mrp>{_NUM})\s+(?P<pu>{_NUM})\s+"
    rf"(?P<rate>{_NUM})\s+(?P<value>{_NUM})\s+(?P<net>{_NUM})\s+(?P<amount>{_NUM})\s*$"
)
_TAIL8 = re.compile(
    rf"^(?P<name>.*?\S)\s+(?P<qty>{_NUM})\s+(?P<free>{_NUM})\s+(?P<mrp>{_NUM})\s+"
    rf"(?P<pu>{_NUM})\s+(?P<rate>{_NUM})\s+(?P<value>{_NUM})\s+(?P<net>{_NUM})\s+"
    rf"(?P<amount>{_NUM})\s*$"
)


def _f(tok):
    """strip thousands commas and a single trailing flag letter -> clean number."""
    return re.sub(r"[a-zA-Z]$", "", tok.replace(",", "")).strip()


def _skip(compact):
    return (
        compact.startswith("suntrader")
        or compact.startswith("gstin")
        or compact.startswith("shop")
        or compact.startswith("page")
        or compact.startswith("listofsaleby")
        or compact.startswith("mfr:")
        or compact.startswith("datefrom")
        or compact.startswith("sr.datedocno")
        or compact.startswith("s/wsupport")
        or compact.startswith("total:")
        or compact.startswith("grandtotal")
    )


def parse_r15_suntraders_saleby_party_docno(text):
    H = ["Party Name", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    party = ""

    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            continue
        compact = re.sub(r"\s+", "", s.lower())

        # wrapped date tail: the year "2026" left over from "02-06-\n2026".
        # It is sometimes trailed by an overflowed item-name fragment when the
        # product name is too long for one line, e.g. the line "11.11 ... Sofidew
        # Baby Moistur Cream {100 ..." wraps its pack to the NEXT line as
        # "2026 Gm}". Re-attach that fragment to the previous item row's name so
        # the pack is not lost, and NEVER let it fall through to the band test
        # (otherwise "Gm}" would be mistaken for a party heading).
        if re.match(r"^2026\b", s):
            frag = s[4:].strip()
            if frag and rows:
                rows[-1][1] = (rows[-1][1] + " " + frag).strip()
            continue
        if _skip(compact):
            continue

        # ---- item row -------------------------------------------------------
        mi = _ITEM.match(s)
        if mi and party:
            rest = mi.group("rest")
            m8 = _TAIL8.match(rest)
            m7 = _TAIL7.match(rest)
            m = None
            # prefer the 8-number (FREE-present) shape only when it is a real
            # column split (Free is an integer-ish free-goods count); otherwise
            # fall back to the 7-number (no-FREE) shape.
            if m8:
                m = m8
                free = _f(m8.group("free"))
            elif m7:
                m = m7
                free = "0"
            if m:
                name = m.group("name").strip()
                qty = _f(m.group("qty"))
                amount = _f(m.group("amount"))
                rows.append([party, name, qty, free, amount])
                continue

        # ---- party band -----------------------------------------------------
        mb = _BAND.match(s)
        if mb and re.search(r"[A-Za-z]", s):
            party = mb.group("name").strip()

    return H, rows
