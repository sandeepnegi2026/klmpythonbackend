import io
import re

import pdfplumber

# ---------------------------------------------------------------------------
# KLM "Group Vs Customer Details" — CUSTOMER-BANDED sibling of
# r15_klm_group_vs_customer_icode. Same report title and the SAME column header
#   ItemName Icode Ipack Town DocDate BillNo Batch MRP BQty BFree Rate NValue NetValue
# but the report is grouped by CUSTOMER: each customer name prints on its own band
# line and the ITEMS it bought are the data rows beneath it — the INVERSE of the
# product-banded r15 dialect (where items band and customers are the data rows).
# M.K. MEDICAL AGENCIES and BHAVYA MEDICAL AGENCIES ship this.
#
# The r15 parser mis-reads these two ways: (1) it assigns item -> party_name and
# customer -> product_name (inverted), and (2) it mangles Town/Rate/NValue because its
# column x-anchors are hardcoded to SRI SUBRAHMANYA's coordinates, which sit ~5-10px
# right of M.K./BHAVYA (e.g. Icode x0 171 vs 165, NValue 638 vs 628) so NValue bled
# into the Rate bucket and a leading glyph fell off Town/Rate.
#
# Fix here: (1) DERIVE the column x-boundaries from THIS file's own header row, so M.K.
# and BHAVYA each get anchors that fit their layer, and (2) assign party <- band
# (customer), product <- the ItemName column of each data row.
#
# Field map (SACRED — qty and value never crossed):
#   band (customer)     -> party_name
#   ItemName column     -> product_name
#   Town                -> party_location
#   Ipack               -> pack
#   DocDate             -> invoice_date
#   BillNo ("MK 705")   -> invoice_number
#   Batch               -> batch_no
#   MRP -> mrp; BQty -> qty; BFree -> free_qty; Rate -> rate;
#   NValue -> amount (== round(BQty*Rate, 2)); NetValue -> net_amount
# Icode is the KLM internal item code and is NOT emitted. Party sale report -> sales
# side only.
#
# Reconcile: NValue == round(BQty*Rate, 2) on every priced row, and the per-customer
# subtotal line (bare "3.00 969.15 1,143.60") == sum(BQty)/sum(NValue)/sum(NetValue).
# ---------------------------------------------------------------------------

H = [
    "Party Name",
    "Location",
    "Product Name",
    "Pack",
    "Date",
    "Invoice Number",
    "Batch",
    "MRP",
    "Qty",
    "Free",
    "Rate",
    "Amount",
    "Net Amount",
]

_DATE = re.compile(r"\b\d{1,2}/[A-Za-z]{3}/\d{2,4}\b")
_MONEY = re.compile(r"^-?[\d,]+\.\d{1,2}$")
_NUMISH = re.compile(r"^-?[\d,]+(?:\.\d+)?$")

# header column tokens (left -> right) and their canonical bucket names
_HDR_TOKENS = ["ItemName", "Icode", "Ipack", "Town", "DocDate", "BillNo",
               "Batch", "MRP", "BQty", "BFree", "Rate", "NValue", "NetValue"]
_HDR_COLS = ["item", "icode", "ipack", "town", "date", "bill",
             "batch", "mrp", "bqty", "bfree", "rate", "nvalue", "netvalue"]


def _fnum(tok):
    try:
        return float(str(tok).replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _fmt(x):
    return "%.2f" % x


def _cluster(chars, tol=3.0):
    cs = sorted(chars, key=lambda c: (c["top"], c["x0"]))
    lines, cur, ct = [], [], None
    for c in cs:
        if ct is None or abs(c["top"] - ct) <= tol:
            cur.append(c)
            if ct is None:
                ct = c["top"]
        else:
            lines.append(cur)
            cur, ct = [c], c["top"]
    if cur:
        lines.append(cur)
    return lines


def _line_text(line):
    out, prev = [], None
    for c in sorted(line, key=lambda c: c["x0"]):
        if prev is not None and c["x0"] - prev > 1.6:
            out.append(" ")
        out.append(c["text"])
        prev = c["x1"]
    return "".join(out)


def _derive_cols(page):
    """Column x-boundaries from THIS page's header row. edge[i] = x0 of the next
    header token, so a char is assigned to the first column whose edge exceeds its x0.
    Returns [(name, edge), ...] + a trailing catch-all, or None if no header row."""
    words = page.extract_words()
    rows = {}
    for w in words:
        rows.setdefault(round(w["top"]), []).append(w)
    hdr = None
    for _top, ws in rows.items():
        texts = {w["text"] for w in ws}
        if "ItemName" in texts and "Icode" in texts and "NetValue" in texts:
            hdr = ws
            break
    if not hdr:
        return None
    x0 = {}
    for w in sorted(hdr, key=lambda w: w["x0"]):
        if w["text"] in _HDR_TOKENS and w["text"] not in x0:
            x0[w["text"]] = w["x0"]
    if not all(t in x0 for t in _HDR_TOKENS):
        return None
    starts = [x0[t] for t in _HDR_TOKENS]
    # NetValue's right edge = first header word past it (spldis/dis column), else a gap
    nv = x0["NetValue"]
    right = [w["x0"] for w in hdr if w["x0"] > nv + 1]
    nv_edge = min(right) if right else nv + (nv - x0["Rate"])
    cols = []
    for i, name in enumerate(_HDR_COLS):
        edge = starts[i + 1] if i + 1 < len(starts) else nv_edge
        cols.append((name, edge))
    cols.append(("spl", 1e9))
    return cols


def _col_of(x0, cols):
    for name, edge in cols:
        if x0 < edge:
            return name
    return "spl"


def _bucketize(line, cols):
    buckets = {name: [] for name, _ in cols}
    for c in sorted(line, key=lambda c: c["x0"]):
        buckets[_col_of(c["x0"], cols)].append(c)
    out = {}
    for name, _ in cols:
        chunk = buckets[name]
        s, prev = [], None
        for c in sorted(chunk, key=lambda c: c["x0"]):
            if prev is not None and c["x0"] - prev > 1.6:
                s.append(" ")
            s.append(c["text"])
            prev = c["x1"]
        out[name] = "".join(s).strip()
    return out


def _is_furniture(joined):
    up = re.sub(r"\s+", "", joined).lower()
    return (
        up.startswith("mkmedical")
        or up.startswith("bhavya")
        or up.startswith("d.no")
        or up.startswith("groupvscustomer")
        or up.startswith("itemname")
        or up.startswith("page")
    )


def _clean_party(s):
    """A customer band prints in the narrow ItemName column, so it is often truncated
    with a trailing '(' or partial code; drop that and stray leading punctuation."""
    s = re.sub(r"\s*\(.*$", "", s)
    s = s.strip(" .,-*")
    return re.sub(r"\s{2,}", " ", s).strip()


def parse_klm_group_vs_customer_custbanded(text, file_bytes=None):
    rows = []
    if not file_bytes:
        return H, rows

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        cols = None
        party = ""
        for page in pdf.pages:
            derived = _derive_cols(page)
            if derived is not None:
                cols = derived
            if cols is None:
                continue
            chars = page.chars
            if not chars:
                continue
            for line in _cluster(chars):
                s = _line_text(line).strip()
                if not s or _is_furniture(s):
                    continue

                if not _DATE.search(s):
                    # bare-number line = per-customer subtotal -> skip;
                    # a text line = the next customer band
                    if re.search(r"[A-Za-z]", s) and not re.match(r"^[\d,.\s]+$", s):
                        party = _clean_party(s)
                    continue

                cols_ = _bucketize(line, cols)
                product = re.sub(r"\s{2,}", " ", cols_["item"].strip())
                ipack = cols_["ipack"].strip()
                town = cols_["town"].strip()
                date_tokens = [t for t in cols_["date"].split() if _DATE.match(t)]
                date = date_tokens[0] if date_tokens else ""
                bill = cols_["bill"].strip()
                batch = cols_["batch"].strip()

                # The six numeric columns are right-aligned, NOT under their left-aligned
                # header labels, so char-bucketing splits them (e.g. "542.03" straddles the
                # Rate boundary -> "54"|"2.03"). Read them from the flat line instead: the
                # row's trailing decimal tokens are, in order,
                #   MRP BQty BFree Rate NValue NetValue [spldis spldisamt]
                # (BillNo and an integer Batch carry no decimal, so _MONEY excludes them).
                money = [t for t in s.split() if _MONEY.match(t)]
                if len(money) < 6:
                    continue
                mrp, bqty, bfree, rate, nvalue, netvalue = money[:6]

                if not party or not product:
                    continue
                if bqty == "" and bfree == "":
                    continue

                rows.append([
                    party,
                    town,
                    product,
                    ipack,
                    date,
                    bill,
                    batch,
                    _fmt(_fnum(mrp)),
                    _fmt(_fnum(bqty)),
                    _fmt(_fnum(bfree)),
                    _fmt(_fnum(rate)),
                    _fmt(_fnum(nvalue)),
                    _fmt(_fnum(netvalue)),
                ])

    return H, rows
