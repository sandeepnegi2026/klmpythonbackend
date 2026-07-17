"""Marg/MVGold "Stock and Sales Statement" — browser/app-printed export
(KAKADE AGENCIES, per KLM division: COSMO / COSMOCOR / COSMOQ / DERMA /
DERMACOR / PED / PHARMA).

The page opens with a print-to-HTML timestamp banner
("6/29/26, 5:49 PM Stock and Sales Statement"), the vendor block, a
"Company : KLM <DIV>" band, a date range, then a MULTI-ROW header whose top
labels wrap over three lines and whose Qty/Value sub-labels sit on a fourth:

    Opst Purc S.R. Sale Sale P.R. Exp Purc Exp Sale Exp Sale Cl. Cl. Near.Exp
                             Non-              Non-
    Product Name Unit         Mov              Mov
    Qty  Qty  Qty  Qty  Value Qty  Qty  Qty  Value Qty  Value 60Days Value Qty

Each data row carries EXACTLY 14 trailing numeric tokens (zero cells print an
explicit '0' / '0.00', so the count never varies), in this fixed order:

  #  header column                       canonical field
  1  Opst Qty          (opening)         opening_stock
  2  Purc Qty          (purchase)        purchase_stock
  3  S.R. Qty          (sales return)    sales_return
  4  Sale Qty                            sales_qty
  5  Sale Value                          sales_value
  6  P.R. Qty          (purchase return) purchase_return
  7  Exp Purc Qty      (Non-Mov purc)    exp_damage   (expiry/non-moving inflow)
  8  Exp Sale Qty      (Non-Mov sale q)  ignored
  9  Exp/Non-Mov Sale Value              ignored
  10 Cl. Qty           (closing)         closing_stock
  11 Cl. Value                           closing_stock_value
  12 Cl. Non-Mov 60Days                  ignored
  13 Cl. Non-Mov Value                   ignored
  14 Near.Exp Qty                        ignored (near-expiry qty; no canonical)

Reconciliation (verified across all 8 KAKADE files, 100%):
    closing = opening + purchase + S.R. - sales - P.R.
The simpler opening + purchase - sales = closing holds 100% on 7/8 files and
94% on DERMACOR (2 rows carry genuine S.R./P.R. movement), so mapping #3 ->
sales_return and #6 -> purchase_return is load-bearing, not cosmetic.

Because the header is multi-row and the columns are tightly packed (~20 px
apart), a flat token-index map would be brittle to the small per-file x-shift.
The text layer, however, extracts cleanly — every product row ends in the same
14 numbers with no blank interior cells — so we cluster words into visual rows
by top-position and pop the trailing 14 numeric tokens in x-order. Everything
to the left of those numbers is Product Name + Unit, split by x-position (the
Unit column starts at x0 ~= 145). Footer lines ("Total Sale Value ...",
"Total Closing Value ...", "file:///..."), the wrapped header, and the vendor
block all carry fewer than 14 trailing numbers and are skipped for free.
"""
import io
import re

# The Unit column (30GM, 10 TAB, 1*3TAB, 10'S, 4 CAP, ...) begins at x0 ~= 145;
# Product Name tokens live at x0 22..~121. Split the pre-number head on this x.
_UNIT_X_MIN = 140.0

_NUM_RE = re.compile(r"^-?\d[\d,]*\.?\d*$")


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _cluster_rows(words, tol=4):
    """Group words into visual rows: tokens whose top is within `tol` px of the
    cluster's first top belong together (folds sub-line jitter)."""
    by_top = {}
    for w in words:
        by_top.setdefault(round(w["top"]), []).append(w)
    rows, cur, start = [], [], None
    for top in sorted(by_top):
        if start is None or top - start <= tol:
            if start is None:
                start = top
            cur.extend(by_top[top])
        else:
            rows.append(cur)
            cur, start = list(by_top[top]), top
    if cur:
        rows.append(cur)
    return rows


def parse_marg_stock_sales_expiry_positional(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            for row_words in _cluster_rows(words):
                row_words = sorted(row_words, key=lambda w: w["x0"])
                if not row_words:
                    continue
                # Data rows start at the left margin (Product Name x0 ~= 35).
                # The vendor block, "Company :", date range and every footer
                # line are indented (x0 >= ~240) or lack 14 trailing numbers.
                if row_words[0]["x0"] > 80:
                    continue

                # Pop the trailing run of numeric tokens (right to left).
                nums = []
                head_end = len(row_words)
                for w in reversed(row_words):
                    if _is_num(w["text"]):
                        nums.append(w)
                        head_end -= 1
                    else:
                        break
                if len(nums) != 14:
                    continue
                nums.reverse()

                head = row_words[:head_end]
                name_toks = [w["text"] for w in head if w["x0"] < _UNIT_X_MIN]
                unit_toks = [w["text"] for w in head if w["x0"] >= _UNIT_X_MIN]
                name = " ".join(name_toks).strip()
                if not name:
                    continue

                v = [_to_f(w["text"]) for w in nums]
                (opst, purc, sret, sale_q, sale_v, pret,
                 exp_purc, _exp_sale_q, _exp_sale_v,
                 cl_q, cl_v, _cl60, _cl60v, _nearexp) = v

                # Drop all-zero phantom rows (no movement, no stock, no value):
                # nothing to reconcile and they only add noise.
                if (opst == 0 and purc == 0 and sale_q == 0 and cl_q == 0
                        and cl_v == 0):
                    continue

                records.append({
                    "product_name": name,
                    "pack": " ".join(unit_toks).strip(),
                    "opening_stock": opst,
                    "purchase_stock": purc,
                    "sales_return": sret,
                    "sales_qty": sale_q,
                    "sales_value": sale_v,
                    "purchase_return": pret,
                    "exp_damage": exp_purc,   # Exp/Non-Mov purchase qty (inflow)
                    "closing_stock": cl_q,
                    "closing_stock_value": cl_v,
                })
    return records
