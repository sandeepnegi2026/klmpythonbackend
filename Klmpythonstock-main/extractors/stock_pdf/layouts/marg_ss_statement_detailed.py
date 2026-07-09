"""Marg 'Stock & Sales Statement Detailed' (SRI DURGA SRINIVASA PHARMA & VETS, KLM).

Banded by "Company :KLM (<DIV>)". One numeric row per item, each carrying a leading
item-code token (KACFT, KECC, KMFSDC, SAC10C, KT0.3O) glued to the product name.

Header:
    Product Name | Pack | O.Bal | Purc | S.Ret | Total | Sales | P.Ret | Total |
                                                                ClBal | Cl.Value | Age

The 10 numeric columns after Pack are, in order:
    [0] O.Bal   opening balance (qty)
    [1] Purc    purchases (qty)
    [2] S.Ret   sales return (qty, inflow)
    [3] Total   running total after inflows  -> IGNORED (== O.Bal+Purc+S.Ret)
    [4] Sales   sales (qty, outflow)
    [5] P.Ret   purchase return (qty, outflow)
    [6] Total   total outflow                 -> IGNORED
    [7] ClBal   closing balance (qty)         == O.Bal + Purc + S.Ret - Sales - P.Ret
    [8] Cl.Value closing VALUE (rupees)
    [9] Age     ageing in days                -> IGNORED

Reconciles per row: O.Bal + Purc + S.Ret - Sales - P.Ret == ClBal
(e.g. Episert 40 + 31 + 0 - 36 - 0 = 35 = ClBal). The Cl.Value column is rupees and
must NOT land in a qty field, so this layout owns its own mapping rather than falling
through to the coarse simple4 / stock_simple_7col rules.

Text-based (flat) layout: every column is printed on every row (no blank interiors,
no glyph interleaving), so a line/token parse is sufficient — no positional pass
needed. Modelled on stock_open_pur_sale_free_current.py.
"""
from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)


def _strip_item_code(prod):
    """Drop the leading Marg item-code token glued to the product name.

    The code is a single upper-case, code-like token (e.g. KACFT, KECC, KMFSDC,
    SAC10C, KT0.3O, KXMP100T). It is always the first token and is always followed by
    the real name. Strip it only when it is code-like (all-caps, no lowercase letters)
    AND at least one name token remains, so plain names are never truncated.
    """
    toks = prod.split()
    if len(toks) < 2:
        return prod
    first = toks[0]
    # code-like: contains no lowercase letters, has at least one letter, and is not a
    # pure number (pure numbers are handled by the numeric-tail split, not here).
    has_lower = any(c.islower() for c in first)
    has_alpha = any(c.isalpha() for c in first)
    if not has_lower and has_alpha:
        return " ".join(toks[1:])
    return prod


def parse_marg_ss_statement_detailed(text):
    records = []
    for line in text.splitlines():
        s = line.strip()
        if _skip_line(s):
            continue
        prod, tail, exp = _split_product_numbers(s)
        if not prod:
            continue
        vals = _nums(tail)
        if len(vals) < 10:
            continue
        # take the last 10 columns (guard against a stray leading number in the tail)
        vals = vals[-10:]
        name, pack = _split_product_pack(_strip_item_code(prod))
        if not name:
            continue
        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": vals[0],       # O.Bal
            "purchase_stock": vals[1],      # Purc
            "sales_return": vals[2],        # S.Ret (inflow)
            "sales_qty": vals[4],           # Sales (outflow)
            "purchase_return": vals[5],     # P.Ret (outflow)
            "closing_stock": vals[7],       # ClBal (real closing qty)
            "closing_stock_value": vals[8], # Cl.Value (rupees)
        }
        if exp:
            r["expiry"] = exp
        records.append(r)
    return records
