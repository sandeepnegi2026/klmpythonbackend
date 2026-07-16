"""NAIK AGENCIES 'STOCK & SALES REGISTER' — KLM per-division 17-column positional.

Vendor:  NAIK AGENCIES ("klm17 stock.pdf"; one section per KLM division inside a
         single multi-page PDF: 'Company Code 0039 KLM LABORATORIES PVT LTD (COSMO)',
         '(DERMA)', ... each reprints the two-line column header below).

Header (two physical lines that collapse to a single compact run):

    PRODUCT NAME  PACK  EXPIRY  RATE  OPENING  RECEIPT  RECEIPT FREE  TOTAL
                        DATE                             QTY
    SALE  INST. SALE  FREE  GOODS REPLACE  SALE RETURN  FREE TOTAL  G.R. TO CO.
    CLOSE  ORDER 100%  ORDER 0%  ORDER 0%

Seventeen right-aligned numeric columns after RATE, blanks printed as '-----'
(so the flat text collapses them and a POSITIONAL x-coordinate parser is required
— an order-based popper mis-binds every column because the token count per row
varies with how many cells are blank). Column meaning / reconcile mapping:

    OPENING        -> opening_stock
    RECEIPT (QTY)  -> purchase_stock          (stock inflow)
    RECEIPT FREE   -> purchase_free           (free purchase, inflow)  }
    GOODS REPLACE  -> purchase_free (added)   (replacement goods in)   } both inflow-free
    TOTAL          -> printed cross-check (= OPENING+RECEIPT+RECEIPT FREE+GOODS REPLACE); ignored
    SALE           -> sales_qty                                        }
    INST. SALE     -> sales_qty (added)       (institutional sale)     } both are sales out
    FREE           -> sales_free              (free goods issued, out) }
    GOODS RETURN   -> sales_free (added)      (folded into the SALE-TOTAL outflow block) }
    SALE TOTAL     -> printed cross-check (= SALE+INST+FREE+GOODS RETURN); ignored
    G.R. TO CO.    -> purchase_return         (goods returned to company, outflow)
    CLOSE          -> closing_stock
    ORDER 100/0/0  -> pending-order qtys (informational) -> ignored

Reconcile (verified on every non-zero data row of the sample):
    closing = opening + purchase + purchase_free - purchase_return
                      - sales_qty - sales_free + sales_return
  which here becomes  CLOSE = (OPENING+RECEIPT+RECEIPT FREE+GOODS REPLACE)
                              - (SALE+INST.SALE+FREE+GOODS RETURN)
  e.g. EKRAN 80 HYDRAGEL SUNS: op12 rec12 -> TOTAL24 ; sale15 free3 -> SALE-TOTAL18 ; CLOSE 6 (24-18=6) OK
       HERPIVAL-1000 TAB:       op28 rec17 recfree13 -> TOTAL58 ; sale20 free4 -> SALE-TOTAL24 ; CLOSE 34 OK
       NEVLON-MAX CREAM:        op27 -> TOTAL27 ; sale6 free1 -> SALE-TOTAL7 ; CLOSE 20 OK

Distinct from every other KLM stock layout: this is the only export with a doubled
'RECEIPT / RECEIPT FREE' inflow pair AND an 'INST. SALE'+'FREE'+'GOODS RETURN'
outflow triple feeding a printed SALE-TOTAL, plus the 'G.R. TO CO.' column. The
'marg_stock_long' fallback it currently lands on mis-reads every column (product,
opening and closing all come back null) -> 100% false SANITY_FAILED.

GATE TOKEN (compact, spaces + newlines stripped, lowercased), unique to this header:
    'receiptreceiptfreetotalsaleinst.freegoodssaleg.r.close'
(the OPENING..CLOSE header-1 run with the doubled RECEIPT and the INST./FREE/GOODS/
SALE/G.R./CLOSE tail). No other stock_pdf header carries a back-to-back
'receiptreceiptfree' so it cannot steal an existing GREEN file.
"""
import io
import re

# Header line-1 label tokens (in printed left->right order) that anchor the numeric
# columns we care about. RECEIPT and SALE and FREE appear twice; we resolve those by
# x-position order rather than by text, so the anchor list below is built positionally.
_HDR1_RUN = ("OPENING", "RECEIPT", "RECEIPT", "FREE", "TOTAL",
             "SALE", "INST.", "FREE", "GOODS", "SALE", "G.R.", "CLOSE",
             "ORDER", "ORDER", "ORDER")

# left->right canonical name for each of the 17 numeric columns.
_COLS = (
    "opening",        # 0  OPENING
    "receipt",        # 1  RECEIPT QTY
    "receipt_free",   # 2  RECEIPT FREE
    "goods_replace",  # 3  GOODS REPLACE (free repl in)
    "total",          # 4  TOTAL (cross-check)
    "sale",           # 5  SALE
    "inst_sale",      # 6  INST. SALE
    "free",           # 7  FREE (issued)
    "goods_return",   # 8  GOODS RETURN (in SALE-TOTAL outflow block)
    "sale_total",     # 9  SALE TOTAL (cross-check)
    "gr_to_co",       # 10 G.R. TO CO.
    "close",          # 11 CLOSE
    "order100",       # 12 ORDER 100%
    "order0a",        # 13 ORDER 0%
    "order0b",        # 14 ORDER 0%
)

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")


def _is_num(t):
    t = t.rstrip(".")
    return bool(t) and bool(_NUM_RE.fullmatch(t.replace(",", ""))) and any(
        c.isdigit() for c in t
    )


def _to_f(t):
    t = t.rstrip(".").replace(",", "")
    try:
        return float(t)
    except ValueError:
        return 0.0


def _cluster_rows(words, tol=3):
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


def _header_col_bounds(row_words):
    """If this visual row is header line 1, return (name_cut, [col_left_edges]) where
    col_left_edges are the 15 numeric-column left boundaries (mid-points between
    consecutive header token x0's), else None.

    We key on the exact printed left->right token sequence (_HDR1_RUN) so the two
    'RECEIPT' and two 'SALE'/'FREE' tokens are disambiguated purely by their order,
    not their text."""
    toks = sorted((w for w in row_words if w["text"] in
                   {"PRODUCT", "NAME", "PACK", "EXPIRY", "RATE"} | set(_HDR1_RUN)),
                  key=lambda w: w["x0"])
    # locate the RATE anchor (start of the numeric band) and the OPENING..ORDER run
    rate = next((w for w in toks if w["text"] == "RATE"), None)
    if rate is None:
        return None
    numeric = [w for w in row_words if w["x0"] > rate["x1"] - 1]
    numeric = sorted(numeric, key=lambda w: w["x0"])
    seq = [w["text"] for w in numeric]
    if seq[:len(_HDR1_RUN)] != list(_HDR1_RUN):
        return None
    heads = numeric[:len(_HDR1_RUN)]  # 15 numeric column header tokens
    # name text ends where RATE begins; RATE value stays with the name/pack side.
    name_cut = heads[0]["x0"] - 6.0     # left edge of OPENING column
    # column left boundary = midpoint between this header token x0 and the previous.
    lefts = []
    prev_right = rate["x1"]
    for w in heads:
        lefts.append((prev_right + w["x0"]) / 2.0)
        prev_right = w["x1"]
    return name_cut, lefts


def _assign(x0, lefts):
    """Return the column index for a numeric token whose left edge is x0 — the last
    column whose left boundary is <= x0 (numbers are right-aligned within the column
    that starts at its left boundary)."""
    idx = -1
    for i, lb in enumerate(lefts):
        if x0 + 1.0 >= lb:
            idx = i
        else:
            break
    return idx


def parse_r15_klm_ss_register_receipt_inst_gr_positional(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        name_cut = None
        lefts = None
        division = ""
        non_moving = False

        for page in pdf.pages:
            words = page.extract_words()
            for row_words in _cluster_rows(words):
                row_words = sorted(row_words, key=lambda w: w["x0"])
                joined = " ".join(w["text"] for w in row_words).strip()
                low = joined.lower()

                found = _header_col_bounds(row_words)
                if found:
                    name_cut, lefts = found
                    non_moving = False
                    continue

                # capture the running division label from the Company-Code band
                if "company code" in low and "klm" in low:
                    m = re.search(r"pvt\s+ltd\s*\(([^)]+)\)", joined, re.I)
                    if m:
                        division = m.group(1).strip()
                    continue

                if lefts is None:
                    continue

                if "non moving" in low or "last 6 months" in low:
                    non_moving = True
                    continue
                if joined.startswith("====") or joined.startswith("----"):
                    continue
                if "** total **" in low or low.startswith("page no"):
                    continue
                if low.startswith("pur.amt") or low.startswith("bill no") \
                        or low.startswith("total net") or "period :-" in low \
                        or low.startswith("naik") or "stock & sales register" in low:
                    continue

                # split name/pack (left of name_cut) from the numeric column tokens.
                # The name band still carries the trailing PACK, EXPIRY DATE and RATE
                # (a bare decimal like 546.100); strip the trailing RATE + EXPIRY so the
                # product name stays clean (pack is recovered downstream by the pipeline).
                name_toks = [w["text"] for w in row_words if w["x0"] < name_cut]
                while name_toks and (
                    re.fullmatch(r"\d{1,3}(?:,\d{3})*\.\d{2,3}", name_toks[-1])  # RATE
                    or re.fullmatch(r"\d{1,2}/\d{2,4}", name_toks[-1])            # EXPIRY
                ):
                    name_toks.pop()
                name = " ".join(name_toks).strip()
                if not name or not re.search(r"[A-Za-z]", name):
                    continue

                cells = {}
                for w in row_words:
                    if w["x0"] < name_cut:
                        continue
                    t = w["text"]
                    if not _is_num(t):
                        continue
                    idx = _assign(w["x0"], lefts)
                    if 0 <= idx < len(_COLS):
                        cells.setdefault(_COLS[idx], _to_f(t))

                op = cells.get("opening", 0.0)
                rec = cells.get("receipt", 0.0)
                rf = cells.get("receipt_free", 0.0)
                grpl = cells.get("goods_replace", 0.0)
                sale = cells.get("sale", 0.0)
                inst = cells.get("inst_sale", 0.0)
                free = cells.get("free", 0.0)
                gret = cells.get("goods_return", 0.0)
                grco = cells.get("gr_to_co", 0.0)
                close = cells.get("close", 0.0)

                # drop all-zero phantom / non-moving catalog rows (no movement, no stock)
                if not any((op, rec, rf, grpl, sale, inst, free, gret, grco, close)):
                    continue

                rec_row = {
                    "product_name": re.sub(r"\s+", " ", name).strip(),
                    "opening_stock": op,
                    "purchase_stock": rec,
                    # both RECEIPT FREE and GOODS REPLACE are free/replacement inflow
                    "purchase_free": rf + grpl,
                    # G.R. TO CO. = goods returned to company (stock out)
                    "purchase_return": grco,
                    # SALE + INST. SALE are both sales out of stock
                    "sales_qty": sale + inst,
                    # FREE (issued) + GOODS RETURN both sit in the SALE-TOTAL outflow block
                    "sales_free": free + gret,
                    "sales_return": 0.0,
                    "closing_stock": close,
                }
                if division:
                    rec_row["division"] = division
                records.append(rec_row)

    return records
