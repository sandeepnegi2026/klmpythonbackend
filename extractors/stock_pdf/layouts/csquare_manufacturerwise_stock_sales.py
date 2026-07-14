"""C-Square 'Manufacturerwise Stock and Sales Report' (UNIVERSAL DRUG LINES, TIRUR).

C-Square export, one file per KLM division band ("Manufacture: KLM LABORATORIES
<DIV> DIV."). Header:

    Item Name | Pack | L.Sale | SaleRate | Op.Qty | Pur.Qty | Sal.Qty | Sal.Val |
    Cr.Qty | Adj | Bal.Qty | Bal.Val

The leading Item/Pack (and sometimes L.Sale / SaleRate) glyph-interleave into the
name in the text layer (e.g. "SUNSCE3E0NG MGEL - 30G1M"), occasionally swallowing
the two informational money columns L.Sale / SaleRate. The TRAILING 8 numerics are
always clean, so we anchor on them rather than the (variable, corrupted) leading
cells:

    [Op.Qty, Pur.Qty, Sal.Qty, Sal.Val, Cr.Qty, Adj, Bal.Qty, Bal.Val]

Column map:
    Op.Qty  -> opening_stock
    Pur.Qty -> purchase_stock
    Sal.Qty -> sales_qty
    Sal.Val -> sales_value
    Cr.Qty  -> sales_return          (credit/return inflow)
    Adj     -> signed adjustment; +Adj folds into purchase_return (subtracts),
               -Adj folds into sales_return (adds), per the klm_sale_stock StkAdj
               convention. (Cr.Qty = Adj = 0 on every observed row.)
    Bal.Qty -> closing_stock
    Bal.Val -> closing_stock_value

Reconcile: closing = opening + purchase + purchase_free + sales_return
                      - sales - sales_free - purchase_return
which reduces here to Bal = Op + Pur - Sal (Cr = Adj = 0). Verified 165/166 data
rows balance (only 'KERAMATE HAIR COLOUR (BLACK)' fails, a glyph corruption in the
source). Sal.Val column sum 161,394.37 and Bal.Val column sum 500,006.53 equal the
seven printed 'Total:' lines' 4th and 5th figures exactly.

The whole report is NOT replicated per page; each of the 7 pages carries its own
product slice, so all pages are parsed. 'Total:' subtotal lines, the 'Manufacture:'
division banners, the masthead and the 'Report Date ...' footer are skipped.
"""
import re

# a token that is purely a (possibly comma-grouped, possibly signed) number
_NUM_TOK = re.compile(r"^-?[\d,]+\.?\d*$")


def _is_num(tok):
    return bool(_NUM_TOK.match(tok)) and any(c.isdigit() for c in tok)


def _to_f(tok):
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return 0.0


def _skip(low):
    return (
        not low
        or low.startswith("manufacture:")
        or low.startswith("total:")
        or low.startswith("report date")
        or low.startswith("item name")
        or "manufacturerwise stock and sales" in low
        or "universal drug" in low
        or "shoping complex" in low
        or "software by c-square" in low
    )


def parse_csquare_manufacturerwise_stock_sales(text):
    records = []
    division = ""
    for raw in text.splitlines():
        s = raw.strip()
        low = s.lower()

        # division band: "Manufacture: KLM LABORATORIES COSMO DIV. 366"
        if low.startswith("manufacture:"):
            m = re.search(r"manufacture:\s*(.*?)(?:\s+\d+)?\s*$", s, re.IGNORECASE)
            if m:
                division = m.group(1).strip()
            continue

        if _skip(low):
            continue

        toks = s.split()
        nums = [t for t in toks if _is_num(t)]
        if len(nums) < 8:
            continue

        # trailing 8 clean numerics
        op, pur, sal, salval, cr, adj, bal, balval = (_to_f(t) for t in nums[-8:])

        # product name = everything before the trailing-8 numeric run
        # (find where the last 8 numeric tokens begin, slice the token list)
        cut = len(toks)
        need = 8
        i = len(toks) - 1
        while i >= 0 and need > 0:
            if _is_num(toks[i]):
                need -= 1
                cut = i
            i -= 1
        name_toks = toks[:cut]
        # Strip the trailing informational L.Sale / SaleRate columns that trail the
        # pack: SaleRate is a decimal, L.Sale an integer. On glyph-clean rows both
        # appear as separate trailing tokens ("... 50GM 0 583.05"); on glyph-merged
        # rows only the SaleRate decimal survives as a token. Peel at most those two
        # so they do not pollute product_name (pack is peeled downstream). Do NOT peel
        # a leading pure-numeric that is actually part of the name's size (guarded by
        # requiring the token to be a decimal / a small int following a decimal).
        if name_toks and _is_num(name_toks[-1]) and "." in name_toks[-1]:
            name_toks = name_toks[:-1]
            if name_toks and _is_num(name_toks[-1]) and "." not in name_toks[-1]:
                name_toks = name_toks[:-1]
        name = " ".join(name_toks).strip()
        if not name:
            name = " ".join(toks[:cut]).strip()
        if not name:
            continue

        purchase_return = adj if adj > 0 else 0.0
        sales_return = cr + (-adj if adj < 0 else 0.0)

        rec = {
            "product_name": name,
            "opening_stock": op,
            "purchase_stock": pur,
            "sales_qty": sal,
            "sales_value": salval,
            "sales_return": sales_return,
            "purchase_return": purchase_return,
            "closing_stock": bal,
            "closing_stock_value": balval,
        }
        if division:
            rec["division"] = division
        records.append(rec)

    return records
