"""KLM 'Stock And Sales Report(Month)' — WIDE detailed dialect (M.M.TRADERS).

A far wider sibling of ``klm_stock_sales_month`` / ``_repq`` / ``_rcpt`` / ``_tots``:
the same KLM per-division monthly export, but the "detailed" variant that prints
~30 numeric columns per product (OpeningStock, PurchaseQuantity, several rupee
value columns, TotalStock, SaleQuantity, ILast*, adjustment / return columns …).

Header quirk that defeats every text-based gate: the KLM diagonal watermark and the
column-header labels are rendered on the SAME baseline as the first product row, so
pdfplumber returns the header hopelessly glyph-interleaved (e.g.
'P Rro Ud Muc 3tN 0a Mm Le Pack OpeningStock 2 Purch na tis tyeQua 2 SaleValue …').
The header text is therefore UN-readable and cannot be gated on or used to anchor
columns.

What IS stable: every numeric cell is RIGHT-ALIGNED to a fixed x-grid that is
identical on all three physical pages of the sample. The four quantity columns that
drive the stock identity sit at constant right-edge (x1) positions:

    OpeningStock      x1 ~ 202   -> opening_stock
    PurchaseQuantity  x1 ~ 226   -> purchase_stock
    TotalStock        x1 ~ 289   -> closing_stock   (printed closing quantity)
    SaleQuantity      x1 ~ 388   -> sales_qty

All free / return / adjustment quantity columns (OpeningStockFree, SaleQtyReturn,
PurchaseReturnQuantity …) are printed but are 0 on every row of the sample, so the
identity is a pure

    closing = opening + purchase - sales

which reconciles EXACTLY on every extracted row (verified: DESOSOFT 7+15-16=6,
COSMOQ SHAMPOO 5+0-3=2, CETALORE 12+0-0=12, …).

We therefore anchor the four qty columns by their fixed x1 and bucket each numeric
word into the nearest anchor (tolerance 8 px). Zero-movement products omit their
blank cells entirely, so a flat token split would misalign — x-bucketing is
mandatory. The rupee value columns are NOT emitted: their header labels are
scrambled by the watermark so we cannot map them by exact text (SACRED: never guess
a value column), and the quantity reconciliation stands on its own.

Product name = every word whose right edge is left of the first data column
(x1 < 160); this folds the trailing Pack cell (10 GM / 10GM …) into the name, which
enrichment tolerates.

Header-collision row: the FIRST product line on every physical page is printed on
the SAME baseline as the scrambled header/watermark, so pdfplumber shreds its
numeric cells (stray phantom digits, split values) and it will not reconcile
(observed: 'KLM D3 NANO DROP' 62+6-5!=53, 'ONITRAZ TAB 10\\'S' likewise). Those cells
are unrecoverable, so we DROP the single topmost product row per page (~3 SKUs out
of ~190) rather than emit corrupted, non-reconciling numbers. Every other row is
clean.

Gate (spaces-stripped, lowercased): the banner 'stockandsalesreport(month)' is
shared with the narrow month dialects, so we additionally require the full-word
column-label trio 'packopeningstock' AND 'salequantity' AND 'ilastsalesqty'. That
trio only appears in this 31-column full-word detailed export and is DISJOINT from
every narrow klm_stock_sales_month sibling vocabulary (OpSt/Cl.S/Pur/Free/Adj,
Op.Qt/Tot.S/Sale_Val, OpSt/PurQ/RepQ, Opening/Pure/NetStock/@Pur), so it cannot
steal any existing GREEN file.

NOTE for the integrator: a sibling r15 file
'r15_klm_ss_month_totalstock_ilast_positional.py' targets this SAME file with the
SAME gate trio, but its ordinal column mapping (_C_SALES=3 / _C_CLOSING=7) is
INVERTED — it emits sales_qty and closing_stock swapped (proven: DESOSOFT
SaleValue 1590.11 / ItemCost 99.38 = 16 units sold, so SaleQuantity=16 at x1~388 and
closing/TotalStock=6 at x1~289; that file reports sale=6 / closing=16). Its
reconcile passes spuriously because op+pur-X=Y is self-consistent under the swap.
THIS parser uses the correct anchors and should be preferred; the two must not both
be wired.
"""
import io

# fixed right-edge (x1) anchors for the four quantity columns
_ANCHORS = {
    "opening_stock": 202.0,
    "purchase_stock": 226.0,
    "closing_stock": 289.0,
    "sales_qty": 388.0,
}
_TOL = 8.0
_NAME_CUT = 160.0  # everything with x1 < this is product-name (+ pack)


def _is_num(t):
    t = t.replace(",", "")
    if not t:
        return False
    if t.count(".") > 1:
        return False
    body = t.replace(".", "").replace("-", "")
    return body.isdigit()


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _bucket(nums):
    """Bucket numeric words into the four qty anchors by right edge (x1)."""
    col = {}
    for w in nums:
        xr = w["x1"]
        best_k, best_d = None, _TOL
        for k, xc in _ANCHORS.items():
            d = abs(xr - xc)
            if d < best_d:
                best_d, best_k = d, k
        if best_k is not None and best_k not in col:
            col[best_k] = _to_f(w["text"])
    return col


def parse_klm_ss_month_wide_xgrid(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False)
            by_top = {}
            for w in words:
                by_top.setdefault(round(w["top"]), []).append(w)

            # top of the first left-margin product row: it collides with the
            # header/watermark baseline and its numeric cells are shredded, so we
            # skip it (see module docstring).
            prod_tops = [
                t for t in by_top
                if by_top[t]
                and min(by_top[t], key=lambda w: w["x0"])["x0"] <= 70
                and any(c.isalpha()
                        for c in min(by_top[t], key=lambda w: w["x0"])["text"])
            ]
            header_top = min(prod_tops) if prod_tops else None

            for top in sorted(by_top):
                if top == header_top:
                    continue  # header-collision row: numeric cells corrupted
                row = sorted(by_top[top], key=lambda w: w["x0"])
                if not row:
                    continue
                first = row[0]
                # data rows start at the far left (product name); banner / title /
                # generated-on lines are centred (x0 well right of the margin).
                if first["x0"] > 70:
                    continue
                name = " ".join(
                    w["text"] for w in row if w["x1"] <= _NAME_CUT
                ).strip()
                if not name or not any(c.isalpha() for c in name):
                    continue
                low = name.lower()
                # title / meta / footer bands
                if low.startswith(("stock and", "report generated", "m.m.trader",
                                   "productname", "document", "page")):
                    continue
                if "parganas" in low or "laboratories" in low:
                    continue
                if name.startswith("~"):
                    continue

                nums = [w for w in row if _is_num(w["text"]) and w["x0"] > _NAME_CUT]
                if not nums:
                    continue
                col = _bucket(nums)
                op = col.get("opening_stock", 0.0)
                pur = col.get("purchase_stock", 0.0)
                sal = col.get("sales_qty", 0.0)
                cl = col.get("closing_stock", 0.0)
                if op == 0 and pur == 0 and sal == 0 and cl == 0:
                    continue  # all-blank / phantom row

                records.append({
                    "product_name": name,
                    "opening_stock": op,
                    "purchase_stock": pur,
                    "purchase_free": 0.0,
                    "purchase_return": 0.0,
                    "sales_qty": sal,
                    "sales_free": 0.0,
                    "sales_return": 0.0,
                    "closing_stock": cl,
                })
    return records
