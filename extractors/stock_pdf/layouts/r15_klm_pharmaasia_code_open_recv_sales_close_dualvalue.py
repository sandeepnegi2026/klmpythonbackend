"""PHARMA ASIA DISTRIBUTOR 'Stock Statement' — KLM (<DIV>) coded 6-column export.

Vendor:  PHARMA ASIA DISTRIBUTOR (KLM divisions; e.g. 'KLM ( DERMA ) Jun-26').
File:     '.../PHARMA ASIA DISTRIBUTORS/Stock report/KLM DERMA.pdf'

This is the SAME report as r15_pharma_asia_simpleformat (sibling KLM.pdf), but this
export's text layer paints the Product Description run and the Packing run over
OVERLAPPING x-ranges (Description x~106-238, Packing x~156-208). Any x-sorted read
(extract_text / extract_words) therefore interleaves the two runs:

    'CANROLFIN1 C5GREMA M'   <- 'CANROLFIN CREAM' + '15GM'
    'Stock StatemPreinntt D(Saimtep 2le4F/o06rm/2a0t2)6'
                             <- 'Stock Statement (SimpleFormat)' + 'Print Date 24/06/2026'

The names are NOT scrambled in the source: in CONTENT-STREAM order the chars read
cleanly ('2440 CANROLFIN CREAM', then a backward x-jump, then '30GM   8 ...').
So this parser rebuilds each row from page.chars kept in stream order:

  * split each line's char stream into RUNS wherever x jumps BACKWARD (>1pt);
  * run 1 = '<Code> <Product Description>'  (strip the 2-6 digit code + any '*');
  * later-run tokens whose right edge sits at least one column-gap LEFT of the
    Opening anchor = the printed Packing cell;
  * numeric cells still bind POSITIONALLY: right-aligned tokens bucket to the
    header-derived right anchors (Opening/Receipt/Sales/Closing/SalesVal/StockVal,
    ~51pt apart, window _TOL) exactly as before — that bucketing already
    reconciled CLOSING = OPENING + RECEIPT - SALES on every row.

Header (printed once at the top of the section):

    Code  Product Description  Packing  Opening  Receipt  Sales  Closing  Sales Value  Stock Value

SIX numeric columns:
    Opening      -> opening_stock
    Receipt      -> purchase_stock
    Sales        -> sales_qty
    Closing      -> closing_stock
    Sales Value  -> sales_value          (money — NOT a quantity)
    Stock Value  -> closing_stock_value  (money)
Vendor identity (canonical sanity):  CLOSING = OPENING + RECEIPT - SALES.

Why a dedicated positional parser (NOT generic / simple4):
  * leading numeric Code column slides simple4/generic column binding;
  * interleaved Packing digits ('10 0 GM', '130 1 0') leak into the qty columns
    under a flat-text read (100% false SANITY_FAILED under generic);
  * TWO money columns (Sales Value + Stock Value) break the last-four heuristic.

Detect gate: the compact column-header run 'openingreceiptsalesclosingsalesvaluestockvalue'
survives the interleave intact, but the '(simpleformat)' banner does NOT (it renders
interleaved with 'Print Date'), so the r15_pharma_asia_simpleformat gate can never fire
for this file. Gate on the header run + 'pharma asia distributor' + NOT '(simpleformat)',
placed immediately AFTER the simpleformat gate — the clean-text sibling keeps routing to
r15_pharma_asia_simpleformat, this parser only receives the interleaved dialect.
"""
import io
import re

# Data-value right-edge anchors (x1) read from the header; a numeric token binds to the
# column whose right edge it is nearest, within this window. Columns are ~51pt apart and
# printed numbers right-align a few points RIGHT of their header token, so a ~26pt window
# binds each number to the correct column without reaching a neighbour.
_TOL = 26.0

_HDR_ORDER = ("OPENING", "RECEIPT", "SALES", "CLOSING")

# '<Code> <name>' / '<Code>*<name>' at the head of the stream-order description run.
_CODE_NAME = re.compile(r"^(\d{2,6})\*?\s*(.+)$")


def _to_f(t):
    t = t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return 0.0


def _is_num(t):
    t = t.replace(",", "")
    if not t:
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False


def _header_anchors(row_words):
    """If this word row is the column header, return the ordered per-column right
    anchors (x1) for OPENING/RECEIPT/SALES/CLOSING + the two money columns, plus the
    OPENING x0 (the name/number boundary). Else None.

    The header prints 'Sales' twice (the SALES qty column and the 'Sales Value' money
    column) and 'Value' twice ('Sales Value', 'Stock Value'), so we resolve columns by
    x position rather than by unique text."""
    ups = [(w["text"].upper(), w) for w in row_words]
    names = {t for t, _ in ups}
    if not all(t in names for t in _HDR_ORDER):
        return None
    if "VALUE" not in names or "STOCK" not in names:
        return None

    # first (leftmost) OPENING / RECEIPT / CLOSING tokens
    def first(tok):
        cand = [w for t, w in ups if t == tok]
        return min(cand, key=lambda w: w["x0"]) if cand else None

    op = first("OPENING")
    rec = first("RECEIPT")
    cls = first("CLOSING")
    if not (op and rec and cls):
        return None
    # SALES qty = the SALES token left of CLOSING; 'Sales Value' SALES is right of it.
    sales_toks = sorted((w for t, w in ups if t == "SALES"), key=lambda w: w["x0"])
    sal = next((w for w in sales_toks if w["x0"] < cls["x0"]), None)
    if sal is None:
        return None
    # Sales Value right edge = the 'Value' token of the pair whose left neighbour is the
    # second 'Sales'; Stock Value right edge = the 'Value' token after 'Stock'.
    value_toks = sorted((w for t, w in ups if t == "VALUE"), key=lambda w: w["x0"])
    stock_tok = first("STOCK")
    if len(value_toks) < 2 or stock_tok is None:
        return None
    stock_val = min(value_toks, key=lambda w: abs(w["x0"] - stock_tok["x1"]))
    sales_val = next((w for w in value_toks if w is not stock_val), None)
    if sales_val is None:
        return None

    anchors = [
        ("OPENING", op["x1"]),
        ("RECEIPT", rec["x1"]),
        ("SALES", sal["x1"]),
        ("CLOSING", cls["x1"]),
        ("SALES_VALUE", sales_val["x1"]),
        ("STOCK_VALUE", stock_val["x1"]),
    ]
    # name/number boundary: a touch left of the OPENING column's left edge.
    name_cut = op["x0"] - 12.0
    return anchors, name_cut


def _stream_runs_by_top(page):
    """Group page.chars by line (rounded top) KEEPING content-stream order, then split
    each line into runs wherever x jumps backward (>1pt): the writer paints the
    Code+Description run first, then jumps back left to paint Packing, then the
    numeric cells. Returns {rounded_top: [run, ...]}, each run a list of chars."""
    lines = {}
    for c in page.chars:
        lines.setdefault(round(c["top"]), []).append(c)
    runs_by_top = {}
    for top, cs in lines.items():
        runs, cur = [], [cs[0]]
        for prev, ch in zip(cs, cs[1:]):
            if ch["x0"] < prev["x0"] - 1.0:
                runs.append(cur)
                cur = [ch]
            else:
                cur.append(ch)
        runs.append(cur)
        runs_by_top[top] = runs
    return runs_by_top


def _run_tokens(run, gap=2.5):
    """Split one stream run into visual tokens on space chars and x-gaps > `gap`
    (digits inside one cell advance ~5.6pt with ~0 gap; neighbouring cells sit
    tens of points apart but carry NO space char between them in the stream)."""
    toks, cur = [], []
    for ch in run:
        if ch["text"].isspace():
            if cur:
                toks.append(cur)
                cur = []
            continue
        if cur and (ch["x0"] - cur[-1]["x1"]) > gap:
            toks.append(cur)
            cur = []
        cur.append(ch)
    if cur:
        toks.append(cur)
    return toks


def parse_r15_klm_pharmaasia_code_open_recv_sales_close_dualvalue(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        anchors = None       # persists across pages once the header is seen
        name_cut = None

        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            by_top = {}
            for w in words:
                by_top.setdefault(round(w["top"]), []).append(w)
            runs_by_top = _stream_runs_by_top(page)

            for top in sorted(by_top):
                row_words = sorted(by_top[top], key=lambda w: w["x0"])
                joined = " ".join(w["text"] for w in row_words).strip()
                low = joined.lower()

                hdr = _header_anchors(row_words)
                if hdr:
                    anchors, name_cut = hdr
                    continue
                if anchors is None:
                    continue

                # banners / section-band / grand-total (no product, or value-only)
                if low.startswith("pharma asia") or low.startswith("stock statement"):
                    continue
                if low.startswith("klm ") and "(" in low:
                    # 'KLM ( DERMA ) Jun-26' division band — no product numbers
                    continue

                runs = runs_by_top.get(top) or []
                if not runs:
                    continue

                # ---- product name: stream-order description run (run 1) ----
                run1 = "".join(c["text"] for c in runs[0]).strip()
                m = _CODE_NAME.match(run1)
                if not m:
                    # masthead / division band / grand-total footer: no leading Code
                    continue
                name = re.sub(r"\s+", " ", m.group(2).lstrip("*")).strip()
                if len(name) < 2 or not re.search(r"[A-Za-z]{2}", name):
                    continue

                # ---- packing: later-run tokens left of the numeric band ----
                # one full column-gap left of the Opening right anchor, so no
                # right-aligned Opening quantity can ever be eaten as pack.
                pack_cut = anchors[0][1] - (anchors[1][1] - anchors[0][1])
                pack_parts = []
                for r in runs[1:]:
                    for tk in _run_tokens(r):
                        if tk[-1]["x1"] <= pack_cut:
                            pack_parts.append("".join(c["text"] for c in tk))
                pack = " ".join(pack_parts).strip()

                # ---- numeric cells: unchanged positional right-anchor bucketing ----
                col_tokens = [w for w in row_words if w["x1"] > name_cut]
                vals = {}
                for w in col_tokens:
                    t = w["text"]
                    if not _is_num(t):
                        continue
                    x1 = w["x1"]
                    best, bestd = None, _TOL
                    for cname, ax in anchors:
                        d = abs(x1 - ax)
                        if d < bestd:
                            bestd, best = d, cname
                    if best is None:
                        continue
                    vals.setdefault(best, _to_f(t))

                records.append({
                    "product_name": name,
                    "pack": pack,
                    "opening_stock": vals.get("OPENING", 0.0),
                    "purchase_stock": vals.get("RECEIPT", 0.0),
                    "sales_qty": vals.get("SALES", 0.0),
                    "closing_stock": vals.get("CLOSING", 0.0),
                    "sales_value": vals.get("SALES_VALUE", 0.0),
                    "closing_stock_value": vals.get("STOCK_VALUE", 0.0),
                })

    return records
