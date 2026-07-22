import re

# ---------------------------------------------------------------------------
# CENTRAL AGENCIES (Calicut) "Stock And Sales Report" — KLM sub-stockist,
# BlueFox Systems ERP. One file covers all KLM divisions, banded by an all-caps
# "KLM COSMO" / "KLM COSMOCOR" / "KLM COSMOQ" / ... heading.
#
# Two-row column header:
#   Op.  Pur  Pur   Sale Sale Repl Ret. Adj  Sale                 Bal.
#   SlNo Product Name  LMS Qty Qty F.Qty Qty F.Qty Qty BR/E Qty Qty  Sale Value F.Value Qty Bal.Val
#
# so each data line carries a leading SlNo, a "<Product Name>-<Pack>" (glued by a
# hyphen), then a DENSE run of exactly 14 numeric cells (zeros printed, not
# blanked):
#   [0] LMS   [1] Op.Qty   [2] Pur.Qty   [3] Pur.F.Qty   [4] Sale.Qty
#   [5] Sale.F.Qty   [6] Repl.Qty   [7] Ret.BR/E   [8] Adj.Qty   [9] (net Sale Qty)
#   [10] Sale Value   [11] F.Value   [12] Bal.Qty (closing)   [13] Bal.Val (closing value)
#
# Verified identity Op + Pur - Sale - Sale.F (+/- Adj) = Bal on every reference
# row (e.g. EKRAN 80: 0+42-18=24; MELBOOST TAB: 0+153-65-7=81). Numbers are
# COMMA-GROUPED ("10,642.92"), which the shared NUM_RE rejects, so this parser
# tokenises with its own comma-aware number pattern instead of _split_product_numbers.
#
# Flat single-page text (no blank interior cells), so a plain text tokeniser
# suffices — no positional parsing needed.
# ---------------------------------------------------------------------------

# Cells are zero-printed and comma-grouped ("10,642.92"); the signed Adj.Qty cell
# ([8]) may be NEGATIVE ("-5"), so the token walk MUST accept a leading '-' — else
# the walk halts at the Adj cell, collects <14 vals, and the whole product row is
# dropped (SUNANDA/TELLY: rows with a -ve Adj were silently lost).
_NUMTOK = re.compile(r'^-?\d[\d,]*(?:\.\d+)?$')
_SLNO = re.compile(r'^(\d+)\s+(.+)$')


def _f(t):
    try:
        return float(t.replace(',', ''))
    except ValueError:
        return 0.0


def parse_central_stock_sales(text):
    records = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = _SLNO.match(s)          # every item row starts with a numeric SlNo
        if not m:
            continue                # band headers ("KLM COSMO"), totals, furniture
        toks = m.group(2).split()
        vals = []
        # pop the trailing 14 numeric cells; the glued "<name>-<pack>" tail is
        # non-numeric (carries a unit) and stops the walk, so a numeric strength
        # token earlier in the name ("EKRAN 80") is never mistaken for a value.
        while toks and _NUMTOK.match(toks[-1]) and len(vals) < 14:
            vals.insert(0, toks.pop())
        if len(vals) != 14 or not toks:
            continue
        prodpack = " ".join(toks).strip()
        if '-' in prodpack:
            name, pack = prodpack.rsplit('-', 1)
            name, pack = name.strip(), pack.strip()
        else:
            name, pack = prodpack, ""
        n = [_f(v) for v in vals]
        records.append({
            "product_name": name,
            "pack": pack,
            "opening_stock": n[1],
            "purchase_stock": n[2],
            "purchase_free": n[3],
            "sales_qty": n[4],
            "sales_free": n[5],
            "sales_value": n[10],
            "closing_stock": n[12],
            "closing_stock_value": n[13],
        })
    return records
