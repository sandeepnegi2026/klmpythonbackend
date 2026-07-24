"""KLM/Marg "Areawise Partywise Sales Summary" (Gujarat / PALANPUR parties).

Shape (per group):
    A071 - ABC MEDICINES, PALANPUR          <- PARTY BAND  "CODE - NAME, CITY"
    LULIZOL CREAM{30GM} 30GM KLDERMACOR 193 193   <- PRODUCT  name|pack|make|May|Total
    (1+0) (1+0)                             <- PAREN  "(qty+free)" repeated per column
    ...
    Total of A071 : 1009 1009               <- group total (value), skipped
    (7+0) (7+0)                             <- group total (qty+free), skipped
    Grand Total : 999948 999948             <- file value total, skipped

The value columns (May and Total) are identical (single-period report), so the
product AMOUNT is the last number on the product line. Quantity + free live ONLY
in the "(N+M)" sub-line that immediately follows each product line. Product names
frequently wrap onto a following name-only line (no pack/make/numbers) which sits
BETWEEN the product line and its "(N+M)" line — those are folded back into the name.

Page breaks routinely split a product from its "(N+M)" sub-line: the vendor/address/
title/column-header block is printed BETWEEN them. That page furniture must be
skipped WITHOUT dropping the pending product, so the paren on the next page still
pairs with its product (else that product's qty/free are lost).

Interior columns are frequently blank and the value columns are right-aligned, so
we parse by word x-position (pdfplumber extract_words) rather than flat text:
    name  x0 < 145 | pack 145..195 | make 195..270 | values x0 >= 270
Party is split name-before-comma / city-after-comma (Gujarat convention).
"""
import io
import re

_PAREN_RE = re.compile(r"\((\d+)\s*\+\s*(\d+)\)")
_PAREN_ONLY_RE = re.compile(r"^(?:\(\d+\s*\+\s*\d+\)\s*)+$")
_BAND_RE = re.compile(r"^([A-Z0-9][A-Z0-9 ]{0,7}?)\s*-\s*(.+?)\s*$")
_TOTAL_RE = re.compile(r"^total\s+of\b", re.I)
_GRAND_RE = re.compile(r"^grand\s+total\b", re.I)
# report/page furniture that repeats at every page top (order-independent)
_PAGE_HDR_RE = re.compile(r"\bpage\s+\d+\s+of\s+\d+\b", re.I)
_PIN_RE = re.compile(r"-\s*\d{6}\b")  # address PIN, e.g. "PALANPUR - 385001"

# column x-bucket boundaries (px), derived from the printed header anchors
_PACK_X = 145.0
_MAKE_X = 195.0
_VAL_X = 270.0


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _is_num(t):
    return bool(re.fullmatch(r"-?\d[\d,]*\.?\d*", t)) and any(c.isdigit() for c in t)


def _cluster_rows(words, tol=4):
    """Group words into visual rows by `top` (handles 1-2px sub-line jitter)."""
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


def _split_party(raw):
    """Party band 'NAME, CITY' -> (name, city). Name-before-last-comma, area =
    last comma segment; degrade gracefully when no comma is present."""
    s = re.sub(r"\s+", " ", raw or "").strip()
    if "," in s:
        head, _, tail = s.rpartition(",")
        return head.strip(" ,.-"), tail.strip(" ,.-")
    return s.strip(" ,.-"), ""


def _is_furniture(joined, low):
    """Repeating page-top furniture (vendor name, address, year/page, title,
    column header). Returns True to SKIP without disturbing a pending product."""
    if _PAGE_HDR_RE.search(joined):                      # "... Page 7 of 24"
        return True
    if low.startswith("year :") or low.startswith("year:"):
        return True
    if low.startswith("period") or ":01-" in low or "period :" in low:
        return True
    if "areawise partywise" in low or "sales summary" in low:
        return True
    if low.startswith("product name") and "make" in low:  # column header
        return True
    if low.startswith("area :") or low.startswith("area:"):
        return True
    if low.startswith("notes"):
        return True
    if low.startswith("admin ") or low.startswith("admin\t"):
        return True
    if _PIN_RE.search(joined) and "," in joined:          # address line w/ PIN
        return True
    return False


def parse_areawise_partywise_summary_pdf(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Pack", "Make", "Qty", "Free", "Amount"]
    if not file_bytes:
        return headers, []

    import pdfplumber

    rows = []
    party_name = party_area = ""
    vendor_hdr = None      # the vendor-name line (first line of page 1), skipped verbatim
    # pending product awaiting its (N+M) sub-line: [name, pack, make, amount]
    pending = None

    def flush_with(qty, free):
        if pending is None:
            return
        name = re.sub(r"\s+", " ", pending[0]).strip()
        rows.append([party_name, party_area, name, pending[1], pending[2],
                     qty, free, pending[3]])

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            for row_words in _cluster_rows(page.extract_words()):
                row_words = sorted(row_words, key=lambda w: w["x0"])
                joined = " ".join(w["text"] for w in row_words).strip()
                if not joined:
                    continue
                low = joined.lower()

                # capture the vendor-name header line once (top of page 1)
                if vendor_hdr is None and not rows and pending is None \
                        and party_name == "" and not _PAREN_RE.search(joined) \
                        and not _is_furniture(joined, low):
                    vendor_hdr = joined
                    continue
                if vendor_hdr is not None and joined == vendor_hdr:
                    continue  # repeated vendor-name line -> furniture, keep pending

                # --- PAREN sub-line: (N+M) [ (N+M) ] -> supplies qty/free -------
                if _PAREN_ONLY_RE.match(joined):
                    pm = _PAREN_RE.search(joined)
                    if pending is not None:
                        flush_with(_to_f(pm.group(1)), _to_f(pm.group(2)))
                        pending = None
                    # else: group-total paren -> ignore
                    continue

                # --- group / grand total: closes the current product ------------
                if _GRAND_RE.match(joined) or _TOTAL_RE.match(joined):
                    if pending is not None:
                        flush_with(0.0, 0.0)
                        pending = None
                    continue

                # --- page furniture: skip WITHOUT clearing pending --------------
                if _is_furniture(joined, low):
                    continue

                # --- PARTY BAND: 'CODE - NAME, CITY' at left margin, no value ---
                nums = [w for w in row_words
                        if _is_num(w["text"]) and (w["x0"] + w["x1"]) / 2.0 >= _VAL_X]
                bm = _BAND_RE.match(joined)
                if bm and " - " in joined and not nums and "," in bm.group(2):
                    code = bm.group(1).strip()
                    if re.fullmatch(r"[A-Z0-9][A-Z0-9 ]{0,7}", code):
                        if pending is not None:      # paren-less trailing product
                            flush_with(0.0, 0.0)
                            pending = None
                        party_name, party_area = _split_party(bm.group(2))
                        continue

                # --- PRODUCT line: value number(s) in the value column ----------
                if nums:
                    name_toks, pack_toks, make_toks, val_toks = [], [], [], []
                    for w in row_words:
                        cx = (w["x0"] + w["x1"]) / 2.0
                        if cx >= _VAL_X and _is_num(w["text"]):
                            val_toks.append(w)
                        elif cx >= _MAKE_X:
                            make_toks.append(w["text"])
                        elif cx >= _PACK_X:
                            pack_toks.append(w["text"])
                        else:
                            name_toks.append(w["text"])
                    name = " ".join(name_toks).strip()
                    if not name:
                        continue
                    amount = _to_f(val_toks[-1]["text"]) if val_toks else 0.0
                    if pending is not None:          # prior product w/o paren
                        flush_with(0.0, 0.0)
                    pending = [name, " ".join(pack_toks).strip(),
                               " ".join(make_toks).strip(), amount]
                    continue

                # --- NAME-WRAP continuation: text-only line (no value nums, not
                #     furniture, not a band) between product and its paren --------
                if pending is not None:
                    pending[0] = (pending[0] + " " + joined).strip()
                    continue

    # flush a final dangling product (paren-less)
    if pending is not None:
        flush_with(0.0, 0.0)

    return headers, rows
