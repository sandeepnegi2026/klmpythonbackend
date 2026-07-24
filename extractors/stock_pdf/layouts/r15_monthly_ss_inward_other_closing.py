"""GAYATRI PHARMA 'Monthly Sales and Stock Statement' (Marg-family, KLM division).

A vendor dropped this stock statement into a "Party report" slot folder; by content
it is a stock report and reconciles on the stock identity.

Column header (single visual row):

  Product Name | Packing | Opening | Inward | Sales | Other | Closing   (+ a trailing
  one-char E/N flag: E = Short Expiry, N = Non Moving Stock — NOT a number column)

Gate token (spaces-stripped, lowercased, contiguous header run):
    "packingopeninginwardsalesotherclosing"
This run (Inward + Other + Closing together) is unique to this export and does not
collide with the Marg 'MONTHLY STOCK & SALES STATEMENT' variant
(marg_monthly_ss_statement_pdf), whose header carries Purchase / Goods Ret. / Total In /
Purc. Ret. / Balance instead.

Reconciliation (verified on the qty rows AND the printed "Total Values ... PRate" control
row):
    Closing = Opening + Inward - Sales + Other
so Inward is a purchase inflow (+), Sales is a sales_qty outflow (-), and "Other" is a
SIGNED adjustment column (customer returns / write-offs — negative in this file). It maps
to the +sales_return slot so its printed sign is preserved:
    closing = opening + purchase - sales_qty + sales_return
Every printed row reconciles exactly under this mapping.

Interior blank cells collapse in the PDF text layer, so the numeric-word count per row
varies (2..4) and flat trailing-slice mis-aligns columns. We read word x-positions with
pdfplumber, take the header labels' RIGHT edges (x1) as anchors (the 5 numeric columns are
right-aligned, so every value in a column shares its right edge), and bucket each numeric
word by the midpoint between consecutive anchors. The trailing E/N flag is a letter, not a
number, so it is never bucketed. The "Total Values ... PRate" row and the
"List of Products WithOut Stock" / "Pending Debit Note's" footer blocks are skipped.
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")
# header labels that uniquely identify this export's column row
_HEADER_TOKENS = ("Opening", "Inward", "Sales", "Other", "Closing")


def _is_num(t):
    t = t.replace(",", "")
    return bool(_NUM_RE.fullmatch(t)) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _header_anchors(words):
    """Return the 5 numeric-column right-edge (x1) anchors if this row is the header."""
    x1 = {}
    for w in words:
        x1.setdefault(w["text"], w["x1"])
    if not all(tok in x1 for tok in _HEADER_TOKENS):
        return None
    return {
        "opening": x1["Opening"],
        "inward": x1["Inward"],
        "sales": x1["Sales"],
        "other": x1["Other"],
        "closing": x1["Closing"],
    }


def _cluster_rows(words, tol=6):
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


_COL_ORDER = ["opening", "inward", "sales", "other", "closing"]

_SKIP_NAME_RE = re.compile(
    r"^(product\b|total\b|grand\b|company\b|division\b|period\b|year\b|page\b|"
    r"gst\b|pan\b|contact\b|monthly\b|opening\b|closing\b)", re.I
)
# once the product table ends these footer blocks begin; stop parsing.
_FOOTER_RE = re.compile(
    r"list of products|pending debit|purchase bills|total values|"
    r"short expiry|non moving", re.I
)


def parse_r15_monthly_ss_inward_other_closing(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        anchors = None
        bounds = None
        name_cut = None
        closing_right = None
        for page in pdf.pages:
            words = page.extract_words()
            table_open = anchors is not None
            for row_words in _cluster_rows(words):
                row_words = sorted(row_words, key=lambda w: w["x0"])
                found = _header_anchors(row_words)
                if found:
                    anchors = found
                    table_open = True
                    xs = [anchors[c] for c in _COL_ORDER]
                    bounds = [(xs[i] + xs[i + 1]) / 2.0 for i in range(len(xs) - 1)]
                    # numeric run begins left of the Opening right edge; the Packing
                    # column sits well left of the first numeric column.
                    name_cut = anchors["opening"] - 40
                    # a small margin right of Closing to admit its value; nothing sits
                    # further right except the one-char E/N letter flag (not numeric).
                    closing_right = anchors["closing"] + 20
                    continue
                if not table_open:
                    continue

                left_text = " ".join(
                    w["text"] for w in row_words
                    if ((w["x0"] + w["x1"]) / 2.0) < name_cut
                ).strip()
                low = left_text.lower()

                # footer block reached -> stop consuming this (single-table) export
                if _FOOTER_RE.search(low):
                    table_open = False
                    anchors = None
                    continue
                if not left_text or _SKIP_NAME_RE.match(low):
                    continue

                nums = [
                    (w["x1"], w["text"])
                    for w in row_words
                    if _is_num(w["text"])
                    and w["x1"] > name_cut
                    and w["x1"] <= closing_right
                ]
                if not nums:
                    continue

                col = {}
                for rx, t in nums:
                    idx = 0
                    while idx < len(bounds) and rx >= bounds[idx]:
                        idx += 1
                    col[_COL_ORDER[idx]] = _to_f(t)

                opening = col.get("opening", 0.0)
                inward = col.get("inward", 0.0)
                sales = col.get("sales", 0.0)
                other = col.get("other", 0.0)
                closing = col.get("closing", 0.0)

                if (opening == 0 and inward == 0 and sales == 0
                        and other == 0 and closing == 0):
                    continue

                name = " ".join(
                    w["text"] for w in row_words
                    if ((w["x0"] + w["x1"]) / 2.0) < name_cut
                ).strip()
                if not name:
                    continue

                records.append({
                    "product_name": name,
                    "opening_stock": opening,
                    "purchase_stock": inward,     # Inward (purchase inflow, +)
                    "sales_qty": sales,           # Sales (outflow, -)
                    "sales_return": other,        # Other (signed adjustment, +sr slot)
                    "closing_stock": closing,
                })
    return records
