import re

from extractors.stock_pdf.parse_common import _nums, _skip_line
from core.pack_match import extract_pack_from_product as _split_product_pack

# Prompt ERP "Stock Statement (Datewise)" with an explicit numeric **Pack** column
# plus a Sales sub-triplet (Qty / Free / Inst).
#
# Gate token (spaces-stripped, lowercased column-header run, UNIQUE to this format):
#   'packopstkpursalesclstk'  followed by 'qtyqtyqtyfreeinstqtyamounta3mn'
#
# Header:
#   Product Name  Pack  OpStk  Pur   Sales              ClStk        A3Mn  Order(s)
#                              Qty   Qty   Qty Free Inst Qty  Amount
#
# The base `prompt` parser peels Pack out of the product text via
# extract_pack_from_product, but here Pack is often a BARE number ("1") that leaks
# into the numeric tail and shifts every column left (opening<-pack, etc.). Sometimes
# Pack is a text token ("15 GM", "50ML") that IS peeled, so the leading number count
# is not stable row-to-row.  Anchor from the RIGHT instead: after stripping the
# trailing "Order(s)" run ("<A3Mn> 0 / 0 / 0 = 0"), the row ends in a fixed EIGHT
# number core:
#   [-8]=OpStk.Qty [-7]=Pur.Qty [-6]=Sales.Qty [-5]=Sales.Free [-4]=Sales.Inst
#   [-3]=ClStk.Qty [-2]=ClStk.Amount [-1]=A3Mn
# Everything before the 8-number core is Product + Pack.
#
# Reconcile: opening + purchase - sales_qty - sales_free (- inst) = closing.
# 'Inst' is a signed instant/adjustment column; folded onto sales_return as a
# subtraction via the negative-return slot is not needed here because it is 0 across
# the corpus, but we route it to sales_return (a decrement in the identity) so a
# non-zero value still reconciles.

_NUM = re.compile(r"^-?[\d,]*\.?\d+$")


def parse_prompt_datewise_pack_free_inst(text):
    """Prompt Stock Statement (Datewise): Pack + Sales(Qty/Free/Inst) + ClStk(Qty/Amount)."""
    records = []
    for line in text.splitlines():
        s = line.strip()
        if not s or _skip_line(s):
            continue
        # data rows start with a serial index
        m = re.match(r"^\d+\s+(\D.*)$", s)
        if not m:
            continue
        body = m.group(1).strip()
        # strip trailing Order(s) run: "<A3Mn> 0 / 0 / 0 = 0"  (keep A3Mn in the core)
        body = re.sub(r"\s+\d+\s*/\s*\d+\s*/\s*\d+\s*=\s*\d+\s*$", "", body).strip()

        toks = body.split()
        # collect the trailing numeric run
        i = len(toks)
        while i > 0 and _NUM.match(toks[i - 1].replace(",", "")):
            i -= 1
        nums = toks[i:]
        head = toks[:i]
        if len(nums) < 8 or not head:
            continue

        core = _nums(nums[-8:])
        # any leading numeric tokens beyond the 8-core belong to Pack (bare-number pack)
        lead = nums[:-8]

        opening = core[0]
        purchase = core[1]
        sales_qty = core[2]
        sales_free = core[3]
        inst = core[4]
        closing = core[5]
        closing_val = core[6]
        # core[7] = A3Mn (3-month avg) -> dropped

        # When Pack was a text token it stays inside `head` and gets peeled by
        # extract_pack_from_product. When Pack was a bare number it lands in `lead`
        # (a single leading integer) -> keep it as the pack and drop it from the name.
        prod_text = " ".join(head).strip()
        name, pack = _split_product_pack(prod_text)
        if not name:
            name = prod_text
        if lead:
            bare_pack = " ".join(lead).strip()
            if not pack:
                pack = bare_pack

        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": opening,
            "purchase_stock": purchase,
            "sales_qty": sales_qty,
            "sales_free": sales_free,
            "sales_return": -inst if inst else 0,
            "closing_stock": closing,
            "closing_stock_value": closing_val,
        }
        records.append(r)

    return records
