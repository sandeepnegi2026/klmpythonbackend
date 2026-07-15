import io
import re

from extractors.stock_pdf.parse_common import _split_product_pack, _to_number

# ---------------------------------------------------------------------------
# Marg "STOCK AND SALES ANALYSIS" — AVA/Apr/OP.BAL/.../B.Sale/SALE/BAL + BVAL/SVAL
# column variant (MALU MEDICO PVT LTD, Sangli; one PDF, KLM division-banded).
#
# Masthead:  "<VENDOR> Page: N of M" / "STOCK AND SALES ANALYSIS From :.. To :.."
# Division band (skipped): "COMPANY GROUP : KLM LABORATORIES ... COMPANY : KLM-<DIV>"
#
# Single-line column header (printed once per page):
#   ITEM NAME  PACK  AVA  Apr  OP.BAL  PUR.  PR.  ADJ.  SR.  B.Sale  SALE  BAL  BVAL  SVAL  N.MOV REMARKS
#
# 14 value columns after PACK. Every ZERO cell prints an explicit '-' AND the
# numbers are RIGHT-ALIGNED, so blank/omitted cells collapse the flat text
# token index -> the coarse stock_simple_7col route mis-binds (sales/closing
# land on the always-'-' cells => sales_qty=0, closing~0, 0% sanity). A
# POSITIONAL parser is required: re-read word x-coordinates via pdfplumber and
# assign each numeric word to the NEAREST column right-edge, taken from the
# header words themselves.
#
# Column meaning (verified by reconciliation on all non-trivial rows across
# every page of the reference file):
#   AVA    - "available" info column           (informational, ignored)
#   Apr    - previous month (April) sale info   (informational, ignored)
#   OP.BAL -> opening_stock
#   PUR.   -> purchase_stock
#   PR.    -> purchase_return   (OUTFLOW -)
#   ADJ.   -> adjustment        (INFLOW +; see note below)
#   SR.    -> sales_return      (INFLOW +)     [proven +: NIOSALIC 36-17+1=20,
#                                               ONITRAZ 80-72+8=16, KLMITE 13+20-7+2=28]
#   B.Sale - bill/scheme-sale count            (informational, ignored)
#   SALE   -> sales_qty         (OUTFLOW -)
#   BAL    -> closing_stock
#   BVAL   -> closing_stock_value  (rupees — VALUE, never a qty field)
#   SVAL   -> sales_value          (rupees — VALUE, never a qty field)
#   N.MOV / REMARKS - trailing text/flag columns (ignored)
#
# Reconcile identity (== triage sanity op+pur+pf-pr-sal-sf+sr):
#   BAL = OP.BAL + PUR. - PR. + ADJ. + SR. - SALE
# holds exactly on every SR-bearing / purchase-bearing row of the reference PDF.
#
# ADJ. note: ADJ. is 0 on every row of the reference file, so its sign is not
# observable here; the reconcile identity needs it as an INFLOW, and canonical
# has no dedicated inflow-adjustment field, so it is folded into purchase_free
# (the sanity equation's only free-inflow slot) to keep reconcile exact if a
# non-zero ADJ. ever appears. PR. -> purchase_return keeps the outflow slot.
#
# Value columns (BVAL/SVAL) are mapped to *_value fields only, never qty.
# ---------------------------------------------------------------------------

_NUM = re.compile(r"^-?[\d,]+(?:\.\d+)?$|^-$")

# Header token -> logical column index. Right-edge (x1) of each header word is
# the column's right-alignment anchor. AVA/Apr/B.Sale are read but dropped.
_HDR = ("AVA", "Apr", "OP.BAL", "PUR.", "PR.", "ADJ.", "SR.",
        "B.Sale", "SALE", "BAL", "BVAL", "SVAL")
_N = len(_HDR)  # 12 value columns we bin (N.MOV/REMARKS are text, past SVAL)

_FURNITURE = re.compile(
    r"item name|company group|company :|stock and sales analysis|page:|"
    r"total :|opening val|closing val|note :|sale\(apr\)|^\s*sales :",
    re.I,
)


def _lines(words, tol=3.0):
    rows = {}
    for w in words:
        key = round(w["top"] / tol)
        rows.setdefault(key, []).append(w)
    return [sorted(v, key=lambda w: w["x0"]) for _, v in sorted(rows.items())]


def _v(t):
    return 0.0 if t == "-" else (_to_number(t) or 0.0)


def parse_marg_stock_ava_bval_sval(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        col_r = None  # 12 right-edge anchors, re-derived from each page's header
        for page in pdf.pages:
            words = page.extract_words()
            lines = _lines(words)
            for ws in lines:
                texts = [w["text"] for w in ws]
                if "OP.BAL" in texts and "BVAL" in texts and "SVAL" in texts:
                    edge = {}
                    for w in ws:
                        # 'N.MOVREMARKS' can glue onto SVAL region; only the exact
                        # header labels we care about are used as anchors.
                        if w["text"] in _HDR:
                            edge[w["text"]] = w["x1"]
                    if all(h in edge for h in _HDR):
                        col_r = [edge[h] for h in _HDR]
                    break
            if col_r is None:
                continue

            sval_edge = col_r[-1]  # SVAL right edge; drop text past it (N.MOV/REMARKS)
            opbal_edge = col_r[2]  # OP.BAL right edge; names sit well left of here

            for ws in lines:
                line_text = " ".join(w["text"] for w in ws)
                if _FURNITURE.search(line_text):
                    continue
                nums, name_parts = [], []
                for w in ws:
                    if _NUM.match(w["text"]) and w["x0"] > opbal_edge - 55:
                        # numeric/dash word inside the value band
                        nums.append(w)
                    elif w["x1"] < opbal_edge - 10:
                        name_parts.append(w["text"])
                if not nums or not name_parts:
                    continue
                name = " ".join(name_parts)
                if not re.search(r"[A-Za-z]{2}", name):
                    continue  # band totals / stray fragments

                vals = {}
                for w in nums:
                    if w["x1"] > sval_edge + 20:
                        continue  # N.MOV / REMARKS text past the value band
                    idx = min(range(_N), key=lambda i: abs(col_r[i] - w["x1"]))
                    if abs(col_r[idx] - w["x1"]) <= 18 and idx not in vals:
                        vals[idx] = w["text"]

                # Need at least the closing (BAL, idx 9) present to be a real row.
                if 9 not in vals:
                    continue

                op = _v(vals.get(2, "-"))
                pur = _v(vals.get(3, "-"))
                pr = _v(vals.get(4, "-"))
                adj = _v(vals.get(5, "-"))
                sr = _v(vals.get(6, "-"))
                sale = _v(vals.get(8, "-"))
                bal = _v(vals.get(9, "-"))
                bval = _v(vals.get(10, "-"))
                sval = _v(vals.get(11, "-"))

                pname, pack = _split_product_pack(name)
                records.append({
                    "product_name": pname,
                    "pack": pack,
                    "opening_stock": op,
                    "purchase_stock": pur,
                    "purchase_free": adj,          # ADJ. inflow (0 in reference file)
                    "purchase_return": pr,
                    "sales_qty": sale,
                    "sales_return": sr,
                    "closing_stock": bal,
                    "closing_stock_value": bval,
                    "sales_value": sval,
                })
    return records
