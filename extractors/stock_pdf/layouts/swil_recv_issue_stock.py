"""SwilERP 'Sales & Stock Statement' — 9-column Receipt/Issue/Retrn dialect (JAY SHREE).

Two-line header:

  PRODUCT NAME | PACKING | Op.Bal. | Receipt | Retrn | Total | Issue | Retrn | Closing | Dump | Near
                           Qty.      Qty.      Qty    Qty.    Qty.    Qty   Balance  Stock  Expiry

Nine right-aligned integer stat columns follow the product name + packing. The
report title is "Sales & Stock Statement" and the header uses "Op.Bal." (not
"opening"), so it falls through the coarse ``stock statement``+``product`` rule to
``simple4`` (a 4-column Op/Receipt/Issue/Closing parser) which pops only the first
four of the nine numbers and mis-maps every field. This dedicated parser reads all
nine.

Column semantics / canonical mapping (proven: the printed per-division and grand
``TOTAL`` rows reconcile, and every one of the 232 product rows satisfies the
equation below — including rows with a non-zero 2nd Retrn, e.g. KALSID
24 95 0 119 39 24 56 -> 24+95-39-24 = 56):

  Op.Bal   -> opening_stock      (opening qty)
  Receipt  -> purchase_stock     (receipt inflow)
  Retrn(1) -> sales_return       (INFLOW: Total = Op + Receipt + Retrn1)
  Total    -> ignored            (= Op + Receipt + Retrn1, informational)
  Issue    -> sales_qty          (issue outflow)
  Retrn(2) -> purchase_return    (OUTFLOW: Closing = Total - Issue - Retrn2)
  Closing  -> closing_stock      (printed closing balance)
  Dump     -> ignored            (dump stock)
  Near     -> ignored            (near-expiry qty)

  => closing = opening + purchase + sales_return - sales - purchase_return

The PACKING (always an ``N x M`` token, e.g. 1X30GM / 1X10 / 5CAP) sits between the
product name and the nine numbers and is frequently GLUED to the last name word
(``EKRAN 30 SILICON S1X30GM``). Zero-movement cells print an explicit ``0`` (never
blank), so the nine stat columns are the trailing run of exactly nine integer
tokens; the pack — never a bare integer (it carries ``X``/unit letters) — bounds
that run on the left. Division banner rows (single all-caps word) and the header /
``Qty.`` sub-header carry no such run and are skipped; per-division and grand
``TOTAL`` rows do carry nine numbers but their name is ``TOTAL`` and are dropped.
"""
import re

# trailing pack token, possibly glued to the previous name word:
#   1X30GM  1X10  1X60ML  5CAP  1X3
_PACK_RE = re.compile(r"(\d+\s*[xX*]\s*\d+[A-Za-z]*|\d*[xX*]?\d+[A-Za-z]{2,})\s*$")
_INT_RE = re.compile(r"-?\d+$")


def _peel_pack(remainder):
    """Split 'product + glued/spaced pack' into (name, pack)."""
    m = _PACK_RE.search(remainder)
    if not m:
        return remainder.strip(), ""
    name = remainder[:m.start()].strip()
    pack = m.group(1).strip()
    # a pack must contain an 'x'/'*' separator OR trailing unit letters; guard against
    # peeling a bare product number that happens to trail (leave those on the name).
    if not name:
        return remainder.strip(), ""
    return name, pack


def parse_swil_recv_issue_stock(text):
    records = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        toks = s.split()
        # trailing run of pure-integer tokens (the nine stat columns)
        run = []
        for t in reversed(toks):
            if _INT_RE.fullmatch(t):
                run.append(t)
            else:
                break
        run.reverse()
        if len(run) < 9:
            continue
        nums = [int(x) for x in run[-9:]]
        remainder = " ".join(toks[: len(toks) - 9]).strip()
        if not remainder:
            continue
        name, pack = _peel_pack(remainder)
        if not name or name.upper().startswith("TOTAL"):
            continue
        op, rec, r1, _tot, iss, r2, clo, _dmp, _near = nums
        records.append({
            "product_name": name,
            "pack": pack,
            "opening_stock": op,
            "purchase_stock": rec,
            "sales_return": r1,
            "sales_qty": iss,
            "purchase_return": r2,
            "closing_stock": clo,
        })
    return records
