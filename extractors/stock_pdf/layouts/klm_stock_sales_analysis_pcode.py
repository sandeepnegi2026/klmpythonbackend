"""KLM 'STOCK AND SALES ANALYSIS' — P.Code-led per-division statement.

Vendor:  PRABHAT AGENCY (PRABHAT AGENCIES), KLM LABORATORIES divisions
         (DERMACOR / COSMOCOR / ... one COMPANY band per division, all in one PDF).
Format:  flat text PDF (n_rects ~= 4).  Header line, printed once per page:

    P.Code  ITEM NAME  PACK  OP.  Pur.  SP  P.Ret  SALE  SS  S.Ret  Adj.  Cls.Stk  <M1>  <M2>

    where the final two columns are the previous two months' sales (their header
    labels rename with the period — Jun export prints "May Apr", May export prints
    "Apr Mar" — so they MUST be dropped positionally, never by name).

Row shape:
    <P.Code:3+ digits> <ITEM NAME ...> <PACK ...> <11 stat tokens>
    The 11 trailing stat tokens are always present (blank cells print as '-'),
    so the numeric block is a fixed width of 11 tokens counted from the RIGHT:
        [0] OP.      -> opening_stock
        [1] Pur.     -> purchase_stock
        [2] SP       -> purchase_free
        [3] P.Ret    -> purchase_return   (adds Adj, see below)
        [4] SALE     -> sales_qty
        [5] SS       -> sales_free
        [6] S.Ret    -> sales_return
        [7] Adj.     -> SIGNED adjustment; folded into purchase_return so it
                        SUBTRACTS from closing (matching the vendor identity),
                        same convention as klm_sale_stock's StkAdj.
        [8] Cls.Stk  -> closing_stock
        [9] <M1>     -> prev-month sale (DROPPED)
        [10]<M2>     -> prev-month sale (DROPPED)

    The PACK sits between the ITEM NAME and the 11 stats; it may itself contain
    digits and spaces ('1 X 10', '1X5 S', '10 CAP', '150 ML'), so it is recovered
    as whatever lies between the name and the last-11 numeric block via the shared
    _split_product_pack peeler (pack is informational; qty binding is unaffected).

Reconcile (vendor's own identity, folding Adj into P.Ret):
    Cls.Stk = OP + Pur + SP - (P.Ret + Adj) - SALE - SS + S.Ret
    == triage sanity  closing = opening + purchase + purchase_free
                      + sales_return - sales - sales_free - purchase_return.

    PRABHAT KLM S_S-2 (Jun) column sums: OP 1365 / Pur 1853 / SP 0 / P.Ret 99 /
    SALE 1649 / SS 0 / S.Ret 47 / Adj 2 / Cls 1517.  260/262 rows balance; the 2
    residual rows (TECUM, NIOSALIC) are genuine +/-1 vendor misprints.

Detect: gate on the compacted header run containing the unique KLM P.Code column
    vocabulary — 'p.code'+'op.'+'sp'+'p.ret'+'ss'+'s.ret'+'adj.'+'cls.stk' — placed
    before the generic fallback.  These tokens appear in no other stock export.
"""

import re

from extractors.stock_pdf.parse_common import _split_product_pack

# a stat token: integer / decimal / signed, or a bare '-' zero placeholder.
_STAT = re.compile(r"^-?\d+(?:\.\d+)?$|^-$")
# leading P.Code: a 3+ digit item code.
_PCODE = re.compile(r"^\d{3,}$")

_N_STATS = 11  # OP Pur SP P.Ret SALE SS S.Ret Adj Cls M1 M2 (last two dropped)


def _v(tok):
    return 0.0 if tok == "-" else float(tok.replace(",", ""))


def _division_from_line(line):
    """Pull the division name out of a 'COMPANY : KLM (DERMACOR DIV)' band."""
    m = re.search(r"COMPANY\s*:\s*KLM\s*[\({]([^)}\n]+?)\s*DIV[\)\}]", line, re.I)
    if m:
        return m.group(1).strip()
    return None


def parse_klm_stock_sales_analysis_pcode(text, file_bytes=None):
    """Parse the flat-text KLM 'STOCK AND SALES ANALYSIS' P.Code layout.

    The text layer is clean and the 11-token stat block is fixed-width (blanks
    print as '-'), so a pure text parse is reliable — no positional pass needed.
    """
    records = []
    division = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        div = _division_from_line(line)
        if div is not None:
            division = div
            continue

        parts = line.split()
        # A product row starts with a numeric P.Code and ends with 11 stat tokens.
        if not _PCODE.match(parts[0]):
            continue
        if len(parts) < _N_STATS + 2:  # code + at least a name + 11 stats
            continue

        tail = parts[-_N_STATS:]
        if not all(_STAT.match(t) for t in tail):
            continue

        vals = [_v(t) for t in tail]
        op, pur, sp, pret, sale, ss, sret, adj, cls = vals[:9]
        # M1/M2 (vals[9], vals[10]) are previous-month sales — intentionally dropped.

        # Everything between the P.Code and the stat block is 'NAME PACK'.
        middle = " ".join(parts[1:-_N_STATS]).strip()
        if not middle or not re.search(r"[A-Za-z]", middle):
            continue
        name, pack = _split_product_pack(middle)
        name = re.sub(r"\s+", " ", name).strip()
        if not name or len(name) < 2:
            continue

        rec = {
            "product_name": name,
            "pack": pack,
            "division": division,
            "opening_stock": op,
            "purchase_stock": pur,
            "purchase_free": sp,
            # Adj folds into purchase_return so it subtracts from closing, matching
            # the vendor's Cls = OP + Pur + SP - P.Ret - SALE - SS + S.Ret - Adj.
            "purchase_return": pret + adj,
            "sales_qty": sale,
            "sales_free": ss,
            "sales_return": sret,
            "closing_stock": cls,
        }
        records.append(rec)
    return records
