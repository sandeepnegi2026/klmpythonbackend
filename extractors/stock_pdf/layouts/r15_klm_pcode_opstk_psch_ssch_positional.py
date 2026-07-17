"""HMRS PHARMA CARE LLP (KLM ERP) 'STOCK AND SALES STATEMENT'.

Dot-matrix / DOS-style export, one product row per line, with a single-row
column header:

    PCode Product Name Packing OPSTK PURC PSCH IN SALE SSCH OUT STOCK Manufacturer / Divis

Every ZERO cell is BLANK (not printed), so the trailing-token count varies per
row and a flat whitespace split cannot align the movement columns once several
interior cells collapse (e.g. a row with only OPSTK and STOCK prints just two
numbers, and a naive split would bind them to the wrong columns). The numbers are
RIGHT-aligned to fixed x-positions, so this is parsed POSITIONALLY: each numeric
word is bucketed into its column by matching its right edge (x1) to the header
label's right edge. The 8 movement columns are rock-stable across all pages.

Column -> canonical mapping (blank cell = nil = 0):
  OPSTK  -> opening_stock
  PURC   -> purchase_stock     (purchase received, IN)
  PSCH   -> purchase_free      (purchase scheme / free goods received, IN)
  IN     -> sales_return       (inward stock adjustment; the remaining +inflow slot)
  SALE   -> sales_qty          (sold, OUT)
  SSCH   -> sales_free         (sales scheme / free goods issued, OUT)
  OUT    -> purchase_return    (outward stock adjustment; the remaining -outflow slot)
  STOCK  -> closing_stock      (the real closing)

Reconcile (the triage identity opening + purchase + purchase_free - purchase_return
- sales_qty - sales_free + sales_return = closing) holds on every printed row,
verified e.g. CETALORE 5MG 73+60=133; HISTABIL 20MG 4+100-67=37; EVAKLIN 9+IN1-1=9;
NEVLON ACNE 5+10+IN1-3=13. IN and OUT are the two generic single-direction
adjustment columns (IN nearly always 0 or 1, OUT empty in samples); mapping them to
the sign-matching return slots keeps the equation exact without inventing quantity
from a value column.

Gate token (compact, lowercased, spaces stripped column-header run, unique to this
export — no other stock_pdf gate references the PSCH/SSCH scheme pair or this run):
    'opstkpurcpschinsalesschoutstock'

PCode is always x0=20, Manufacturer (KLM ...) always x0>=372, numbers all end by
x1<=371 — so name|pack|numbers|mfr split cleanly on x-position.
"""
import io

import pdfplumber

# header label -> canonical key, in printed left-to-right order; the bucket anchor
# is each label's right edge (x1), to which the right-aligned numbers align.
_COL_SEQUENCE = [
    "opening_stock",   # OPSTK
    "purchase_stock",  # PURC
    "purchase_free",   # PSCH
    "sales_return",    # IN   (inward adjustment)
    "sales_qty",       # SALE
    "sales_free",      # SSCH
    "purchase_return",  # OUT  (outward adjustment)
    "closing_stock",   # STOCK
]
_COL_HEADERS = ["OPSTK", "PURC", "PSCH", "IN", "SALE", "SSCH", "OUT", "STOCK"]

# x-position boundaries (from the stable header):
#   PCode x0=20 | Product Name x0>=49 | Packing x0~150 | numbers x0>=185, x1<=371 |
#   Manufacturer x0>=372.
_NAME_X0 = 45.0   # product name starts here (PCode is the sole word left of it)
_PACK_X0 = 148.0  # packing column
_NUM_X0 = 185.0   # first movement number column starts
_NUM_X1_MAX = 371.5  # STOCK right edge; anything wider is the Manufacturer text

# recognise the header row by its exact column-header token stream
_HEADER_TOKENS = ("PCode", "OPSTK", "PURC", "PSCH", "SALE", "SSCH", "STOCK")


def _is_num_token(t):
    s = t.replace(",", "").rstrip(".")
    return bool(s) and any(c.isdigit() for c in s) and all(
        c.isdigit() or c == "." for c in s
    )


def _to_f(t):
    try:
        return float(t.replace(",", "").rstrip("."))
    except ValueError:
        return 0.0


def _extract_word_rows(file_bytes):
    """Yield [word,...] rows clustered by y-top, x-sorted, across all pages."""
    out = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            by_top = {}
            for w in words:
                key = round(w["top"])
                matched = None
                for k in by_top:
                    if abs(k - key) <= 1:
                        matched = k
                        break
                by_top.setdefault(matched if matched is not None else key, []).append(w)
            for top in sorted(by_top):
                out.append(sorted(by_top[top], key=lambda w: w["x0"]))
    return out


def _header_anchors(row):
    """Return {col_key: right-edge x1} from the OPSTK...STOCK header labels, in order.

    Matches the 8 movement-column labels positionally; PCode/Product/Packing/
    Manufacturer are ignored. Returns None if the 8 labels are not all found.
    """
    by_text = {w["text"]: w for w in row}
    if not all(h in by_text for h in _COL_HEADERS):
        return None
    anchors = {}
    for key, hdr in zip(_COL_SEQUENCE, _COL_HEADERS):
        anchors[key] = by_text[hdr]["x1"]
    return anchors


def _bucket_numbers(nums, anchors):
    """Assign each numeric word to the nearest column by right-edge distance."""
    cols = list(anchors.items())
    out = {}
    for w in nums:
        key = min(cols, key=lambda kv: abs(kv[1] - w["x1"]))[0]
        # if two numbers land on the same column (should not happen with distinct
        # right edges), keep the later/rightmost — harmless, columns are distinct.
        out[key] = _to_f(w["text"])
    return out


def parse_klm_pcode_opstk_psch_ssch_positional(text, file_bytes=None):
    if not file_bytes:
        return []

    records = []
    anchors = None
    for row in _extract_word_rows(file_bytes):
        toks = [w["text"] for w in row]

        # (re)arm anchors on each page's header row
        if all(t in toks for t in _HEADER_TOKENS):
            a = _header_anchors(row)
            if a is not None:
                anchors = a
            continue
        if anchors is None:
            continue

        # first word must be a numeric PCode near x0=20 for a data row
        if not row or not toks[0].replace(".", "").isdigit() or row[0]["x0"] > 40:
            continue

        name_toks = [w["text"] for w in row if _NAME_X0 <= w["x0"] < _PACK_X0]
        pack_toks = [w["text"] for w in row if _PACK_X0 <= w["x0"] < _NUM_X0]
        nums = [
            w for w in row
            if w["x0"] >= _NUM_X0 and w["x1"] <= _NUM_X1_MAX and _is_num_token(w["text"])
        ]

        name = " ".join(name_toks).strip()
        if not name:
            continue

        col = _bucket_numbers(nums, anchors)
        rec = {
            "product_name": name,
            "pack": " ".join(pack_toks).strip(),
            "opening_stock": col.get("opening_stock", 0.0),
            "purchase_stock": col.get("purchase_stock", 0.0),
            "purchase_free": col.get("purchase_free", 0.0),
            "purchase_return": col.get("purchase_return", 0.0),
            "sales_qty": col.get("sales_qty", 0.0),
            "sales_free": col.get("sales_free", 0.0),
            "sales_return": col.get("sales_return", 0.0),
            "closing_stock": col.get("closing_stock", 0.0),
        }

        # skip a fully-empty movement row (all 8 cells blank)
        if not any(rec[k] for k in (
            "opening_stock", "purchase_stock", "purchase_free", "purchase_return",
            "sales_qty", "sales_free", "sales_return", "closing_stock",
        )):
            continue

        records.append(rec)

    return records
