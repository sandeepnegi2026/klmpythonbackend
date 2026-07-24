"""SmartPharma360 'Stock and Sale Report For Reps' — O.stk/T.Stock/Purc/Purc.Ret/
Replace./S.Qty/S.Free/S.Value/S.Ret Qty/S.Ret Fre/Qoh/Value/Age dialect
(PRUDHVI PHARMACEUTICALS, KLM division-banded).

Footer 'Powered by SmartPharma360'; title 'Stock and Sale Report For Reps'.

Gate token (compact, spaces-stripped, lowercased column-header run, unique to
this format):
    'o.stkt.stockpurcpurc.retreplace.s.qtys.free'

Header (13 movement columns after Products+Pack, + an optional Age):
    Products | Pack | O.stk | T.Stock | Purc | Purc.Ret | Replace. |
        S.Qty | S.Free | S.Value | S.Ret Qty | S.Ret Fre | Qoh | Value | Age

The 13 numeric data columns, in order (0-indexed within the window):
    [0]  O.stk        opening_stock        (qty)
    [1]  T.Stock      total_stock          (qty; = O.stk + Purc, IGNORED for recon)
    [2]  Purc         purchase_stock       (qty)
    [3]  Purc.Ret     purchase_return      (qty)
    [4]  Replace.     -> maps to sales_return slot (signed +sr adjustment; 0 here)
    [5]  S.Qty        sales_qty            (qty, outflow)
    [6]  S.Free       sales_free           (qty, outflow)
    [7]  S.Value      sales_value          (rupees)   <- DECIMAL
    [8]  S.Ret Qty    sales_return         (qty, inflow)
    [9]  S.Ret Fre    sales_return_value?  (rupees)   <- DECIMAL (always 0.00 here)
    [10] Qoh          closing_stock        (qty, quantity-on-hand)
    [11] Value        closing_stock_value  (rupees)   <- DECIMAL
    [12] Age          ageing in days       -> IGNORED
Age (a bare integer, [12] here written as trailing after Value) is OPTIONAL — many
rows omit it.

Reconciles per row (qty):
    opening + purchase - purchase_return - sales_qty - sales_free
        + sales_return (S.Ret Qty) + Replace. = Qoh (closing)
e.g. KOJITIN EMULGEL 15gm  5 + 30 - 0 - 21 - 0 + 0 + 0 = 14 = Qoh.

The three RUPEE columns (S.Value [7], S.Ret Fre [9], Value [11]) are always printed
with two decimals ('.XX'); the other ten are integers. This gives a decimal
fingerprint at relative positions {7,9,11} inside the 13-column data window, which we
use to peel a BARE-NUMERIC pack ('10','20','4') off the product text without ever
pulling a value column into a qty field — the pack digit, when present, is absorbed
into the trailing numeric run and would otherwise shift the whole window one slot left
(decimals would then sit at {8,10,12}).

The plain ``stock_qoh`` parser reads a 7-column window (O.Stk/Purc/Tot/Sale/Qoh/
Value/Age) and mis-maps this wider layout wholesale (it landed S.Value=4416.63 in
purchase_stock), so this format owns its own mapping. Gate must fire BEFORE the coarse
``if "qoh" in low: return "stock_qoh"`` rule.
"""
import re

from extractors.stock_pdf.parse_common import (
    _skip_line,
    _split_product_pack,
    _to_number,
)

_NUM = re.compile(r"^-?\d{1,3}(?:,\d{2,3})+(?:\.\d+)?$|^-?\d+(?:\.\d+)?$")
# A bare-numeric or size-style pack that may sit immediately before the data window.
_PACK_TOK = re.compile(r"^(?:\d+|\d*\*\d+|\d+(?:\.\d+)?[A-Za-z]+|[A-Za-z]+\d*)$")


def parse_smartpharma_reps_ostk_replace(text):
    records = []
    division = ""
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue

        # Division band: 'Company Name: KLM - COSMO'
        m = re.match(r"(?i)^company\s+name\s*:\s*(.+)$", s)
        if m:
            div = m.group(1).strip()
            # 'KLM - COSMO' -> 'COSMO'; keep the tail after the last ' - '
            if " - " in div:
                div = div.rsplit(" - ", 1)[-1].strip()
            division = div
            continue

        low = s.lower()
        # Footer / total lines (unique to this export) — skip explicitly.
        if low.startswith("total op") or low.startswith("sale val") or \
           "powered by smartpharma" in low or low.startswith("products pack") or \
           low.startswith("stock sale report") or low.startswith("stock and sale") or \
           low.startswith("page:"):
            continue
        if _skip_line(s):
            continue

        toks = s.split()
        if len(toks) < 14:
            continue

        # Collect the trailing numeric run (right to left). Age (bare int) is optional.
        nums = []
        i = len(toks) - 1
        while i >= 0 and _NUM.match(toks[i]):
            nums.insert(0, toks[i])
            i -= 1
        if len(nums) < 13:
            continue

        # Locate the 13-column data window: the three rupee columns carry a decimal
        # point at relative positions {7,9,11}. Slide the 13-wide window across the
        # trailing numeric run and pick the offset whose decimal fingerprint matches.
        chosen = None
        for start in range(0, len(nums) - 13 + 1):
            win = nums[start:start + 13]
            decs = {j for j, n in enumerate(win) if "." in n}
            if {7, 9, 11}.issubset(decs) and not (decs - {7, 9, 11}):
                chosen = start
                break
        if chosen is None:
            # Fall back to the strict decimal test allowing extra decimals only at
            # {7,9,11}; if still nothing matches this isn't our row.
            continue

        win = nums[chosen:chosen + 13]
        # Tokens left of the window = product words + (optional) leading numeric packs
        # that were part of the trailing run. Reconstruct the product-text tokens.
        left_num_tokens = nums[:chosen]
        head_tokens = toks[: i + 1]  # non-numeric product words
        prod_text = " ".join(head_tokens + left_num_tokens).strip()
        if not prod_text:
            continue

        v = [_to_number(x) or 0.0 for x in win]
        (opening, total_stock, purchase, purch_ret, replace,
         sqty, sfree, sval, sretq, sretf, qoh, clos_val, _age) = v

        # Split product name / pack. The pack may be a bare number ('10') that the
        # generic splitter leaves inside the name — peel a trailing pack-like token.
        name, pack = _split_product_pack(prod_text)
        if not pack:
            wp = name.split()
            if len(wp) >= 2 and _PACK_TOK.match(wp[-1]) and re.search(r"\d", wp[-1]):
                pack = wp[-1]
                name = " ".join(wp[:-1]).strip()
        if not name:
            continue

        r = {
            "product_name": name,
            "pack": pack,
            "opening_stock": opening,          # O.stk
            "total_stock": total_stock,        # T.Stock (= O.stk + Purc)
            "purchase_stock": purchase,        # Purc
            "purchase_return": purch_ret,      # Purc.Ret
            "sales_qty": sqty,                 # S.Qty (outflow)
            "sales_free": sfree,               # S.Free (outflow)
            "sales_value": sval,               # S.Value (rupees)
            "sales_return": sretq + replace,   # S.Ret Qty (inflow) + Replace. adj
            "closing_stock": qoh,              # Qoh (quantity-on-hand)
            "closing_stock_value": clos_val,   # Value (rupees)
        }
        if division:
            r["division"] = division
        records.append(r)
    return records
