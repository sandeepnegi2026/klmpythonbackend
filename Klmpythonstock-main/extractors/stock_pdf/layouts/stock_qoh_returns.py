"""PROFITMAKER (Daxinsoft/Megasoft) 'Stock & Sales Statement Internal New'.

This is the 7-stat-column sibling of ``stock_qoh`` that additionally prints the
sales-return (SRet) and purchase-return (PRet) movement columns — a genuinely
different column ORDER that the plain ``stock_qoh`` parser mis-maps wholesale
(it reads sales<-SRet, closing<-PRet, closing_value<-Qoh). C.D. ASSOCIATES
exports one file per division with this exact header::

    C D ASSOCIATES
    Stock & Sales Statement Internal New
    Product Name Packing Ostk Purc Sale SRet PRet Qoh QohValue
    Company :KLM COSMO DIVISION
    ===========================
    EKRAN AQUA GEL 50GM 8 30 23 2 2 15 3354.55

Each product line is ``<name> [pack] <Ostk> <Purc> <Sale> <SRet> <PRet> <Qoh>
<QohValue>`` — exactly SEVEN trailing stat numbers. We TAIL-anchor the last 7
(``t = vals[-7:]``) so a bare-numeric Packing token that gets popped into the
numeric tail (``HERPIVAL-1000 10 102 100 166 0 0 36 4025.70`` = pack ``10`` then
7 stats) cannot shift the field mapping left. Field map::

    opening_stock       = t[0]   (Ostk)
    purchase_stock      = t[1]   (Purc)
    sales_qty           = t[2]   (Sale)
    sales_return        = t[3]   (SRet)
    purchase_return     = t[4]   (PRet)
    closing_stock       = t[5]   (Qoh)
    closing_stock_value = t[6]   (QohValue)

The row equation ``Qoh = Ostk + Purc + SRet - PRet - Sale`` holds on every row
(i.e. ``closing == opening + purchase + sales_return - purchase_return - sales``,
the triage reconciliation). Negative closings (e.g. ``XEPIBACT 500 TAB … -1
-330.75``) are kept.

Skipped:
  * the column-header line ('Product Name Packing …')
  * division/company bands ('Company :KLM PHARMA DIVION' — caught by SKIP_RE
    'company')
  * per-group / grand Total lines (SUBTOTAL_RE) and pure separators ('====')

This module uses a LOCAL ``_skip`` (idiom copied from
``layouts/marg_sale_closing_pdf.py``) that deliberately OMITS
``parse_common._skip_line``'s historic ``startswith("KLM ")`` guard: here the
'KLM ...' lines are genuine products (``KLM C-1000 20s 30 30 10 0 0 50
14524.13`` etc.) and only the 'Company :KLM ...' band headings must be dropped
(they carry no numeric tail / hit SKIP_RE 'company').
"""
import re

from extractors.stock_pdf.constants import SKIP_RE, SUBTOTAL_RE
from extractors.stock_pdf.parse_common import (
    _nums,
    _split_product_numbers,
    _split_product_pack,
)


def _skip(s):
    """Local skip that (unlike parse_common._skip_line) does NOT drop lines that
    merely start with 'KLM ' — this vendor sells genuine products named KLM
    C-1000 / KLM D3 NANO SHOTS / KLM FX-120 / KLM FX-180, which the shared helper
    would eat. 'Company :KLM ...' division bands carry no trailing stat numbers
    and hit SKIP_RE 'company'; the 7-number requirement in the caller drops any
    other numberless band. Here we only reject genuinely empty/short lines,
    separators, Total rows and the column-header line."""
    if not s or len(s) < 5:
        return True
    if s.startswith("Product Name"):  # the 'Product Name Packing Ostk ...' header
        return True
    if SUBTOTAL_RE.match(s) or SKIP_RE.match(s):
        return True
    if re.match(r"^[\d\s\-]+$", s):  # pure separator / rule line
        return True
    return False


# ---------------------------------------------------------------------------
# Local mend for core.pack_match.extract_pack_from_product over-peels.
#
# The Packing column in these PROFITMAKER files is a SHORT unit token
# ('7TAB', '10s', '15gm', '1*5s', '1', '2 ml', '1 sach' ...) and the word in
# front of it is the tail of the PRODUCT NAME. pack_match's 2-token rule glues
# the two together whenever their concatenation *starts* like a pack (its
# '(TAB|CAP)\d+' alternative is not end-anchored, and '8'+'15s' -> '815s'
# matches the \d+'?S alternative), which drops the trailing name word into
# the pack:  'NIOFINE TAB'|'7TAB'   -> 'NIOFINE'    | 'TAB 7TAB'
#            'KLCEPO 200 TAB'|'1'   -> 'KLCEPO 200' | 'TAB 1'
#            'RESOTEN-NF 8'|'15s'   -> 'RESOTEN-NF' | '8 15s'
# and 'EZACNE SACHET'|'1 sach' is not split at all ('sach' is unknown to
# PACK_RE). Repaired here, gated to this layout only; a (name, pack) pair
# whose pack does not exhibit one of these three signatures is returned
# untouched.
# ---------------------------------------------------------------------------
_FORM_WORD_RE = re.compile(
    r"^(?:TAB|TABS|TABLET|TABLETS|CAP|CAPS|CAPSULE|CAPSULES|OINT|OINTMENT|"
    r"GEL|CREAM|LOTION|SACHET|SYP|SYRUP|DROP|DROPS|POWDER|SOLUTION)$",
    re.I,
)
_BARE_INT_RE = re.compile(r"^\d+$")


def _mend_pack_peel(name, pack):
    toks = pack.split()
    # A) 'TAB 7TAB' / 'TAB 1' / 'TAB 1*5s': a dosage-form word glued in front
    #    of the real pack token is the last word of the product name.
    if len(toks) >= 2 and _FORM_WORD_RE.match(toks[0]):
        return (name + " " + toks[0]).strip(), " ".join(toks[1:])
    # B) '8 15s': bare strength digits + a pack token carrying its own count.
    #    ('15 gm' / '2 ml' / '1 sach' keep their letter-led second token.)
    if len(toks) == 2 and _BARE_INT_RE.match(toks[0]) and toks[1][:1].isdigit():
        return (name + " " + toks[0]).strip(), toks[1]
    # C) blank pack and the name tail is '<n> sach' (PACK_RE knows SACHET but
    #    not the printed abbreviation 'sach') -> that tail IS the pack.
    if not pack:
        nt = name.split()
        if len(nt) >= 3 and _BARE_INT_RE.match(nt[-2]) and nt[-1].lower() == "sach":
            return " ".join(nt[:-2]), " ".join(nt[-2:])
    return name, pack


def parse_stock_qoh_returns(text):
    records = []

    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if _skip(s):
            continue

        prod, tail, exp = _split_product_numbers(s)
        if not prod:
            continue

        vals = _nums(tail)
        if len(vals) < 7:
            # division/company band heading (no trailing numbers) or a stray line
            continue

        # TAIL-anchor the seven stat columns so a bare-numeric Packing token that
        # was popped into the tail (e.g. 'HERPIVAL-1000 10 102 100 166 0 0 36
        # 4025.70') cannot shift the mapping left. Any extra leading popped
        # numbers ARE that bare-numeric pack -> re-append to the product text so
        # _split_product_pack still sees it.
        extra = vals[:-7]
        t = vals[-7:]
        if extra:
            prod = prod + " " + " ".join(tail[: len(extra)])

        name, pack = _split_product_pack(prod)
        name, pack = _mend_pack_peel(name, pack)
        if not name.strip():
            continue

        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": t[0],       # Ostk
            "purchase_stock": t[1],      # Purc
            "sales_qty": t[2],           # Sale
            "sales_return": t[3],        # SRet
            "purchase_return": t[4],     # PRet
            "closing_stock": t[5],       # Qoh
            "closing_stock_value": t[6], # QohValue
        }
        if exp:
            r["expiry"] = exp
        records.append(r)

    return records
