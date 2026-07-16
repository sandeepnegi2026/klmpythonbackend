"""NU SRI SHYAM PHARMACEUTICALS — Marg 'Sales And Stock (Detail)' 3-page-split export.

Vendor: NU- SRI SHYAM PHARMACEUTICALS P LTD. (KLM LABORATORIES divisions). One
report whose column set is too wide for a single A4 portrait page, so Marg splits
each screen of ~10 products across THREE consecutive physical PDF pages that share
the same product ORDER and the same vertical row positions (top y-coordinates):

  Page A  header:  NameToDisplay  Strength  <Group>  OpStock  OpValue  PurchaseQty
  Page B  header:  PurchaseValue  SalesQty  SalesValue  Cl.Stock As On  Cl.Value
                   PurchaseReturnQty  PurchaseRtnValue  SalesReturnQty  SalesReturnValue
  Page C  header:  DumpStock  NearExpiryStock

The three pages repeat A,B,C,A,B,C,... to the end (page_count % 3 == 0). Each product
occupies the SAME `top` on its A/B/C page triple, so the three column-groups are
re-joined by matching row top y-coordinates within the triple.

Why positional (NOT a text/simple parser): pdfplumber's flat text extraction
interleaves the three page bands and, worse, the report leaves a QUANTITY cell BLANK
whenever it is zero (e.g. a product with OpStock 0 prints only OpValue + PurchaseQty,
so the OpStock token is simply absent). Token order per line is therefore not stable;
the meaning is by x-position (each numeric column is right-aligned under its header),
so we bucket every numeric token to the nearest header column anchor.

Column -> canonical stock field (map by exact header text / x-anchor; qty and value
are kept in separate columns — a value is NEVER used as a quantity):
  Page A: OpStock       -> opening_stock
          OpValue       -> (dropped; no canonical opening-value slot)
          PurchaseQty   -> purchase_stock
  Page B: PurchaseValue -> (dropped; always 0.00 in this export, no canonical slot)
          SalesQty      -> sales_qty
          SalesValue    -> sales_value
          Cl.Stock As On-> closing_stock
          Cl.Value      -> closing_stock_value
          PurchaseReturnQty -> purchase_return
          SalesReturnQty    -> sales_return
The 'Group' band (KLM LABORATORIES PVT.LTD. (KLM*_G)) sits in its own middle column
and is captured as `division`. The product code in parentheses stays inside the name;
Strength is captured as `pack`.

Identity: opening + purchase + purchase_free - purchase_return - sales_qty - sales_free
+ sales_return = closing. On this file ~120/165 rows balance exactly; the remainder
carry a printed PurchaseQty of 0.00 while their closing stock exceeds opening (the
vendor's Marg export has an empty Purchase column even though stock grew) — a source
imbalance, not a parse error. No number is fabricated to force balance.

Skipped as non-product: the 'Grand Total' footer row, the repeated column-header rows,
and the 'NU- SRI SHYAM ... / GSTIN / Sales And Stock (Detail) / (From ... Upto ...)'
banner block above each page's header.

Detect: gate on the compact page-A header run 'opstockopvaluepurchaseqty' — a
contiguous column-header run unique to this export. Place it before the coarse
marg/simple fallbacks (it currently mis-detects as 'marg_bordered' -> 0 rows).
"""
import io
import re

# a numeric token is bound to the column whose header x-anchor it is nearest, within
# this window (points). Adjacent columns here are >=40pt apart, so ~14pt is safe.
_TOL = 14.0

# right-aligned numeric columns are identified by their header token x0 (left edge);
# printed numbers share the same left edge as their header token in this Marg export.
# Page A anchors:
_A_OPSTOCK = 393.1
_A_PURQTY = 488.8
# Page B anchors:
_B_SALESQTY = 138.0
_B_SALESVAL = 180.5
_B_CLSTOCK = 233.6
_B_CLVAL = 286.8
_B_PURRET = 340.0
_B_SALRET = 446.3

_NAME_CUT = 290.0   # product name / code text lives left of x0=290
_GROUP_LO = 335.0   # 'Group' band column band
_GROUP_HI = 392.0


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _is_num(t):
    t = (t or "").replace(",", "")
    if not t:
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False


def _near(x, a):
    return abs(x - a) < _TOL


def _rows_by_top(page, ymin=215.0):
    """Group a page's words into rows keyed by rounded top y-coordinate."""
    by_top = {}
    for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
        if w["top"] < ymin:
            continue
        by_top.setdefault(round(w["top"]), []).append(w)
    return by_top


def parse_r15_nu_srishyam_sales_stock_detail_tripage(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages = pdf.pages
        n = len(pages)
        for base in range(0, n - 2, 3):
            pa, pb = pages[base], pages[base + 1]
            # page C (Dump/NearExpiry) carries no reconcile field; skipped intentionally

            rows_a = _rows_by_top(pa)
            rows_b = _rows_by_top(pb)

            for top in sorted(rows_a):
                wa = sorted(rows_a[top], key=lambda w: w["x0"])
                # product name/code = tokens left of the name cut
                name_toks = [w for w in wa if w["x0"] < _NAME_CUT]
                name = " ".join(w["text"] for w in name_toks).strip()
                if not name or not re.search(r"[A-Za-z]", name):
                    continue
                low = name.lower()
                if low.startswith("grand total") or low.startswith("total"):
                    continue
                if low.startswith(("nametodisplay", "sales and stock", "purchasevalue",
                                   "dumpstock", "cl.stock", "namet")):
                    continue

                # Strength / pack: tokens between name cut and the group band
                pack = " ".join(
                    w["text"] for w in wa
                    if _NAME_CUT <= w["x0"] < _GROUP_LO
                ).strip()

                # division / group band: prints as a 5-line stacked block
                # ('KLM','LABORATO','RIES','PVT.LTD.','(KLM*_G)') centred on the product
                # row. Gather every group-column token whose top is within the row block,
                # then rejoin the split 'LABORATO'/'RIES' word.
                grp_toks = []
                for tt, ws2 in rows_a.items():
                    if abs(tt - top) > 24:
                        continue
                    for w in ws2:
                        if _GROUP_LO <= w["x0"] < _GROUP_HI and re.search(r"[A-Za-z]", w["text"]):
                            grp_toks.append((tt, w["text"]))
                grp = " ".join(t for _, t in sorted(grp_toks))
                grp = grp.replace("LABORATO RIES", "LABORATORIES")
                grp = re.sub(r"\s*\(KLM[^)]*\)\s*", " ", grp).strip()
                division = re.sub(r"\s+", " ", grp).strip()

                # numeric page-A columns
                op = pq = 0.0
                for w in wa:
                    if not _is_num(w["text"]):
                        continue
                    if _near(w["x0"], _A_OPSTOCK):
                        op = _to_f(w["text"])
                    elif _near(w["x0"], _A_PURQTY):
                        pq = _to_f(w["text"])

                # matching page-B row (same top)
                sq = sv = cs = cv = prq = srq = 0.0
                for w in rows_b.get(top, []):
                    if not _is_num(w["text"]):
                        continue
                    x = w["x0"]
                    if _near(x, _B_SALESQTY):
                        sq = _to_f(w["text"])
                    elif _near(x, _B_SALESVAL):
                        sv = _to_f(w["text"])
                    elif _near(x, _B_CLSTOCK):
                        cs = _to_f(w["text"])
                    elif _near(x, _B_CLVAL):
                        cv = _to_f(w["text"])
                    elif _near(x, _B_PURRET):
                        prq = _to_f(w["text"])
                    elif _near(x, _B_SALRET):
                        srq = _to_f(w["text"])

                rec = {
                    "product_name": re.sub(r"\s+", " ", name).strip(),
                    "pack": pack,
                    "opening_stock": op,
                    "purchase_stock": pq,
                    "purchase_return": prq,
                    "sales_qty": sq,
                    "sales_value": sv,
                    "sales_return": srq,
                    "closing_stock": cs,
                    "closing_stock_value": cv,
                }
                if division:
                    rec["division"] = division
                records.append(rec)

    return records
