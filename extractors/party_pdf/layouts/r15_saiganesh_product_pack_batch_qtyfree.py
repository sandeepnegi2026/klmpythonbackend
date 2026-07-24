import io
import re

# ---------------------------------------------------------------------------
# SAI GANESH PHARMA (RAIPUR C.G., KLM distributor) — "SALES REPORT",
# product-detail (batch-wise) party sales.
# Source file: SAI GANESH PHARMA/Party report/klmpedia.pdf
#
# The PDF interleaves TWO reports that are ROW-PARALLEL, block for block:
#   * a party summary list  ("PARTY CITY DATE INVNO" -> <name> <city> <dd/mm/yyyy>
#     <invno>") — one row per BILL LINE, each per-party block closed by a bare
#     "0.00" footer;
#   * a product-detail list ("PRODUCT PACK BATCH QTY FREE MRP RATE AMOUNT")
#     grouped per bill, each block closed by an all-zero-but-amount subtotal line
#     "0.00 0.00 0.00 0.00 <bill_total>".
#
# The two sections carry the SAME number of blocks (159) AND the same number of
# rows *within each block* (375 party rows == 375 product rows; block-size
# sequence identical element-for-element). Row j of party-block i therefore
# describes the same bill line as row j of product-block i. So we parse both into
# ordered blocks and ZIP party[i][j] onto product[i][j], attaching Party Name /
# Party Location / Invoice No. / Inv. Date to every product row. The product
# columns are unchanged (parsed exactly as before); only the four party fields
# are appended.
#
# GUARD: the pairing is applied ONLY when the block structure lines up exactly
# (equal block count AND equal per-block row count). On any misalignment we blank
# the party fields — degrading to the original product-only behaviour rather than
# emitting a wrong party name.
#
# GATE token (spaces stripped, lowercased) — the product column header:
#   "PRODUCT PACK BATCH QTY FREE MRP RATE AMOUNT"
#     -> "productpackbatchqtyfreemrprateamount"
#
# COLUMN SPLIT is POSITIONAL by word x0 — the eight product columns are cleanly
# aligned in the source (header x0: PRODUCT 53, PACK 192, BATCH 242, QTY 320,
# FREE 345, MRP 384, RATE 414, AMOUNT 447). A text-based right-to-left peel is
# unsafe because product NAMES themselves end in size tokens ("APPYBUSH SYRUP
# 200ML", "SACCTIK GG ORAL DROP", "ARGICYNE SACHETS 6GM") that would be
# mis-swallowed into the PACK column. Using x-bands the PRODUCT column (x0 < 185)
# and the PACK column (185 <= x0 < 235) never overlap.
#
# Numeric columns are mapped by their fixed x-band, NEVER derived:
#   QTY   (310 <= x0 < 340), FREE (340 <= x0 < 365), MRP (365 <= x0 < 395),
#   RATE  (395 <= x0 < 435), AMOUNT (x0 >= 435).
# Reconcile (the source's own arithmetic): QTY * RATE == AMOUNT on every row,
# and the summed AMOUNT (283387.92) matches the printed grand-total line
# "0.00 0.00 0.00 0.00 283387.92". FREE is a genuine free-QTY column (-> free_qty);
# MRP and RATE are the two price columns; AMOUNT is the net value column.
#
# The party-summary columns share the same page geometry: PARTY name (x0 < 185),
# CITY (185 <= x0 < 310), DATE dd/mm/yyyy (x0 ~355, in the product FREE band) and
# INVNO printed as a float (x0 ~410+). A party row is told apart from a product
# row by the presence of a dd/mm/yyyy DATE token; a product row never carries one.
# ---------------------------------------------------------------------------

H = [
    "Product Name",
    "Pack",
    "Batch",
    "Qty",
    "Free Qty",
    "MRP",
    "Rate",
    "Amount",
    # party fields appended (row-parallel from the party-summary section); these
    # canonicalize exactly to party_name / party_location / invoice_number /
    # invoice_date (see core.canonical PARTY_FIELDS synonyms).
    "Party Name",
    "Party Location",
    "Invoice No",
    "Inv. Date",
]

# Column x0 boundaries (left edge of each column), with tolerance.
# Boundaries derived from the value x0 positions (values are right-aligned, so
# each value's left edge sits a little LEFT of its header's left edge):
#   QTY ~316-322, FREE ~351-352, MRP ~375-381, RATE ~409-415, AMOUNT ~454-460.
_PACK_X0 = 185.0     # product < this <= pack
_BATCH_X0 = 235.0    # pack    < this <= batch
_QTY_X0 = 310.0      # batch   < this <= qty
_FREE_X0 = 340.0
_MRP_X0 = 365.0
_RATE_X0 = 395.0
_AMOUNT_X0 = 435.0

# Party-summary geometry: the CITY column sits between the name and the DATE.
_CITY_MAX_X0 = 310.0  # party name < 185 <= city < 310 <= date/invno

_MONEY = re.compile(r"^-?[\d,]+\.\d{1,2}$")
_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _fnum(tok):
    try:
        return float(str(tok).replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def _row_words(page):
    """Cluster a page's words into visual text rows by 'top' proximity."""
    words = sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"]))
    out = []
    anchor = None
    cur = []
    for w in words:
        if anchor is None or abs(w["top"] - anchor) <= 3.0:
            if anchor is None:
                anchor = w["top"]
            cur.append(w)
        else:
            out.append(sorted(cur, key=lambda x: x["x0"]))
            cur = [w]
            anchor = w["top"]
    if cur:
        out.append(sorted(cur, key=lambda x: x["x0"]))
    return out


def _column_split(ws):
    """Bucket a row's words by x0 into the 8 columns. Returns
    (product, pack, batch, qty, free, mrp, rate, amount) as strings, or None if
    the row is not a valid product line (missing/invalid numeric tail)."""
    prod, pack, batch, qty, free, mrp, rate, amount = [], [], [], [], [], [], [], []
    for w in ws:
        x0 = w["x0"]
        t = w["text"]
        if x0 < _PACK_X0:
            prod.append(t)
        elif x0 < _BATCH_X0:
            pack.append(t)
        elif x0 < _QTY_X0:
            batch.append(t)
        elif x0 < _FREE_X0:
            qty.append(t)
        elif x0 < _MRP_X0:
            free.append(t)
        elif x0 < _RATE_X0:
            mrp.append(t)
        elif x0 < _AMOUNT_X0:
            rate.append(t)
        else:
            amount.append(t)

    qty_s = " ".join(qty).strip()
    free_s = " ".join(free).strip()
    mrp_s = " ".join(mrp).strip()
    rate_s = " ".join(rate).strip()
    amount_s = " ".join(amount).strip()
    prod_s = " ".join(prod).strip()

    # A real product row has decimal QTY, FREE, MRP, RATE and AMOUNT columns and
    # a non-empty product name. This rejects the party-summary rows (a date sits
    # in the QTY band) and the "0.00 0.00 0.00 0.00 <total>" subtotal footers
    # (they carry no product name).
    for s in (qty_s, free_s, mrp_s, rate_s, amount_s):
        if not _MONEY.match(s):
            return None
    if not prod_s:
        return None
    return (
        prod_s,
        " ".join(pack).strip(),
        " ".join(batch).strip(),
        qty_s,
        free_s,
        mrp_s,
        rate_s,
        amount_s,
    )


def _party_split(ws):
    """If ``ws`` is a party-summary row, return (name, location, invno, date);
    else None. A party row carries a dd/mm/yyyy DATE token and a name in the
    product-name band (x0 < 185). Product rows never carry a slash-date token."""
    date = ""
    for w in ws:
        if _DATE.match(w["text"]):
            date = w["text"]
            break
    if not date:
        return None
    name = " ".join(w["text"] for w in ws if w["x0"] < _PACK_X0).strip()
    if not name:
        return None
    location = " ".join(
        w["text"] for w in ws if _PACK_X0 <= w["x0"] < _CITY_MAX_X0
    ).strip()
    # INVNO is printed as a float ("4473.00"); it is an invoice number, so drop a
    # trailing ".00"/",00" cents part and thousands separators -> "4473".
    invno = ""
    for w in ws:
        t = w["text"]
        if _MONEY.match(t):
            invno = t
            break
    if invno:
        invno = invno.replace(",", "")
        if invno.endswith(".00"):
            invno = invno[:-3]
    return (name, location, invno, date)


def _is_bare_money_row(ws):
    """A row made up ONLY of money tokens (>=1). The party section closes each
    per-party block with a lone "0.00"; the product section closes each block with
    "0.00 0.00 0.00 0.00 <total>". Distinguish them by token count."""
    money = 0
    for w in ws:
        if _MONEY.match(w["text"]):
            money += 1
        else:
            return 0
    return money


def parse_r15_saiganesh_product_pack_batch_qtyfree(text, file_bytes=None):
    if not file_bytes:
        return H, []
    import pdfplumber

    # Ordered product rows (identical to the original parser's output), and the
    # same rows re-grouped into blocks closed by the 5-token subtotal footer.
    prod_rows = []
    prod_blocks = []
    cur_prod = []
    # Party rows grouped into blocks closed by the bare "0.00" footer.
    party_blocks = []
    cur_party = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            for ws in _row_words(page):
                party = _party_split(ws)
                if party is not None:
                    cur_party.append(party)
                    continue

                cols = _column_split(ws)
                if cols is not None:
                    # Drop the all-zero subtotal footer defensively (product name is
                    # already required, but guard against any stray).
                    _, _, _, qty, free, _, _, amount = cols
                    if _fnum(qty) == 0.0 and _fnum(amount) == 0.0 and _fnum(free) == 0.0:
                        continue
                    prod_rows.append(list(cols))
                    cur_prod.append(list(cols))
                    continue

                # Not a party row and not a product row: is it a block-closing
                # money-only footer? 1 token closes a PARTY block; >=2 tokens
                # ("0.00 0.00 0.00 0.00 <total>") closes a PRODUCT block.
                money = _is_bare_money_row(ws)
                if money == 1:
                    if cur_party:
                        party_blocks.append(cur_party)
                        cur_party = []
                elif money >= 2:
                    if cur_prod:
                        prod_blocks.append(cur_prod)
                        cur_prod = []
                # any other row (header/noise) is ignored
    if cur_party:
        party_blocks.append(cur_party)
    if cur_prod:
        prod_blocks.append(cur_prod)

    # ---- pair party -> product, block for block, row for row ----------------
    # Only when the block structure matches EXACTLY (same block count AND same
    # per-block row count). Otherwise blank the party fields (degrade to the
    # original product-only behaviour) rather than mis-pair.
    aligned = (
        len(party_blocks) == len(prod_blocks)
        and all(len(pb) == len(qb) for pb, qb in zip(party_blocks, prod_blocks))
    )

    rows = []
    if aligned:
        for pb, qb in zip(party_blocks, prod_blocks):
            for party, prod in zip(pb, qb):
                name, location, invno, date = party
                rows.append(prod + [name, location, invno, date])
    else:
        for prod in prod_rows:
            rows.append(prod + ["", "", "", ""])

    return H, rows
