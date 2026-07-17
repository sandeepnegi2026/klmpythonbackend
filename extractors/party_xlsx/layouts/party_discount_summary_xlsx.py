"""
"PARTY DISCOUNT SUMMARY ON SALES" — a Busy/Marg text export (SAM MEDICOS / KLM)
where the whole report is space-padded fixed-width text crammed into a single column
(one physical line per cell). The party heads a bare name band (no trailing numbers);
each product line is:

    SNo.   P A R T Y   D E S C R I P T I O N   QTY.  GROSS   VOLUME DISCOUNT  ITEM DISCOUNT   BILL      BILL
                                                     AMOUNT   (1)       (2)    (1)      (2)  DISCOUNT   AMOUNT

    AMRITA CLINIC                                                                  <- party band (name only)
    1  GA-6 CREAM 30G      30G Tube   30  2742.00  0.00  0.00  130.52  0.00  0.00  2611.48   <- product line
    ...
    70   9557.90   0.00   0.00   454.96   0.00   0.00   9102.94                    <- per-party subtotal
    GRAND TOTAL  748  107319.25  0.00  0.00  7524.77  0.00  0.00  99794.48         <- grand total

A product line carries a LEADING SNo integer, then the product description (with a pack
token like "30G Tube"/"150ML"), then EIGHT trailing numbers:
    QTY | GROSS AMOUNT | VOL.DISC(1) | VOL.DISC(2) | ITEM.DISC(1) | ITEM.DISC(2) | BILL DISC | BILL AMOUNT

Canonical mapping:  QTY->qty, GROSS AMOUNT->amount, ITEM DISCOUNT(1)->discount_amount,
BILL AMOUNT->net_amount. The per-party subtotal (a bare 8-number line, no description) and
GRAND TOTAL / dashes / page-noise rows are skipped so nothing double-counts.

The generic readers cannot attach the party here (it is a band, not a column) and the
figures live inside one text cell, so marg_busy reads 0 rows.
"""
import re

from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text

_TITLE = "party discount summary"
_NUM_RE = re.compile(r"^-?[\d,]+\.?\d*$")
_DASHES_RE = re.compile(r"^[-=\s]+$")
# EIGHT numeric columns per product / subtotal line.
_NCOL = 8


def _ws(text):
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _is_num(tok):
    return bool(tok) and bool(_NUM_RE.match(tok.replace(",", "")))


def title_matches(rows):
    head = normalize(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    return _TITLE in head


def _find_header(rows):
    """The header spaces out letters ("P A R T Y   D E S C R I P T I O N"); compare on the
    de-spaced form. The GROSS/BILL AMOUNT labels wrap to the next line, so key on the first
    header line's DESCRIPTION + QTY + GROSS signature."""
    for idx, row in enumerate(rows[:15]):
        compact = normalize(" ".join(cell_text(c) for c in row)).replace(" ", "")
        if "description" in compact and "qty" in compact and "gross" in compact:
            return idx
    return None


def _is_page_noise(text):
    n = normalize(text)
    c = n.replace(" ", "")
    if "description" in c and "qty" in c:
        return True
    if "partydiscountsummary" in c:
        return True
    if "endofreport" in c:
        return True
    if c.startswith("continued"):
        return True
    if c.startswith("pageno"):
        return True
    if n.startswith("grand total"):
        return True
    if c.startswith("amount") and "(1)" in c:  # wrapped 2nd header line
        return True
    return False


def detect(rows):
    if not title_matches(rows):
        return False
    header_idx = _find_header(rows)
    if header_idx is None:
        return False
    # Single-column text: the data rows are one cell each (or merged identical). Require a
    # real mix of bare-name bands and 8-number product lines so a columnar sibling never
    # matches on the title alone.
    bands = prods = 0
    for raw in rows[header_idx + 1:]:
        distinct = [c for c in (cell_text(x) for x in raw) if c]
        if not distinct or len(set(distinct)) != 1:
            continue
        text = _ws(distinct[0])
        if not text or _DASHES_RE.match(text) or _is_page_noise(text):
            continue
        toks = text.split()
        nums = 0
        while toks and _is_num(toks[-1]):
            toks.pop()
            nums += 1
        if nums >= _NCOL and toks and not toks[0].lower().startswith(("grand", "total")):
            prods += 1
        elif nums == 0:
            bands += 1
    return bands >= 2 and prods >= 2


def parse_party_discount_summary(rows):
    header_idx = _find_header(rows)
    if header_idx is None:
        return [], {}
    records = []
    current_party = ""
    for raw in rows[header_idx + 1:]:
        distinct = [c for c in (cell_text(x) for x in raw) if c]
        if not distinct or len(set(distinct)) != 1:
            continue
        text = _ws(distinct[0])
        if not text or _DASHES_RE.match(text):
            continue
        if _is_page_noise(text):
            continue
        toks = text.split()
        nums = []
        while toks and _is_num(toks[-1]):
            nums.insert(0, toks.pop().replace(",", ""))
        if len(nums) >= _NCOL:
            # take the RIGHTMOST 8 numbers as the value columns; anything before is
            # description text (or, on a subtotal line, nothing).
            vals = nums[-_NCOL:]
            extra = nums[: len(nums) - _NCOL]  # numeric tokens that belong to the product name
            # subtotal line: no description text and no leading SNo -> just 8 numbers -> skip.
            if not toks:
                continue
            # drop the leading SNo. serial (first token is a bare integer)
            desc_toks = toks[:]
            if desc_toks and _is_num(desc_toks[0]) and "." not in desc_toks[0]:
                desc_toks = desc_toks[1:]
            product = " ".join(desc_toks + extra).strip()
            if product and current_party:
                records.append({
                    "party_name": current_party,
                    "product_name": product,
                    "qty": vals[0],
                    "amount": vals[1],
                    "discount_amount": vals[4],
                    "net_amount": vals[7],
                })
        elif not nums:
            # bare name row = party band (never a subtotal/dashes; those are filtered above)
            if not text.lower().startswith(("grand", "total")):
                current_party = text
    detected = {
        "P A R T Y   D E S C R I P T I O N": "product_name",
        "QTY.": "qty",
        "GROSS AMOUNT": "amount",
        "ITEM DISCOUNT (1)": "discount_amount",
        "BILL AMOUNT": "net_amount",
    }
    return records, detected
