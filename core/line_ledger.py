"""Line-accounting ledger — every source line must be explained, or it is counted.

Why this exists: parsers keep the lines their patterns match and silently drop the
rest; triage grades only the kept rows. On 2026-07-21 marg_register dropped 386 of
2068 item lines (19%) and the file still triaged GREEN CLEAN. The ledger closes
that class of failure structurally: after a parser runs, every non-blank input
line (pdf) or sheet row (xlsx) is classified as exactly one of

    row-CLAIMED   an output row's own values locate it (value-anchored — never
                  the parser's matcher, which would be circular)
    TOTAL         the report's own printed-totals furniture
    NOISE         page furniture, banners, addresses, column headers
    CONTEXT       party/section band that legitimately yields no row but is
                  corroborated by row text (its rows carry the band's name)
    UNEXPLAINED   data-shaped, claimed by nothing -> possible dropped row

`unexplained` is the headline number: the triage gate (UNACCOUNTED_LINES) blocks
GREEN whenever it is materially non-zero. The ledger itself never mutates rows
and runs BEFORE enrichment (enrichment rewrites product names and would break
value anchoring).

Known blind spot (documented by design): a dropped line whose every distinctive
value coincidentally also appears in some kept row is invisible here; the
printed-totals reconcile (core/printed_totals.py) is the aggregate backstop —
a dropped value-bearing row shifts the sum off the vendor's own grand total.

core/ must not import from extractors/, so the noise vocabulary lives here (same
rule as triage's _CENSUS_NOISE copy).
"""
import re

LEDGER_VERSION = 1

CAPS = {"max_lines": 20000, "max_rows": 20000, "sample": 8}

# --------------------------------------------------------------------------- #
# shared regexes
# --------------------------------------------------------------------------- #
_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")
_DEC_RE = re.compile(r"-?\d[\d,]*\.\d{1,2}\b")
_ID_RE = re.compile(r"[A-Z0-9][A-Z0-9/-]{4,}")
_ALPHA_RUN = re.compile(r"[A-Za-z]{3,}")

_RULE_RE = re.compile(r"^[\s\-=_*.]{3,}$")

# Printed-totals furniture: label totals, Marg MF doc-type summaries, bare
# numeric grand lines, labelled footer pairs.
#   * "sub\s*tot(?:al)?"  -> Marg "Product Sub Tot 45 20 3406.44 1571.6" (manufacturerwise_billwise)
#   * "customer\s*totals" -> "Customer Totals : 12504.80 27.00" (klm_company_customer_invoice)
#   * op-stk / sale-prv    -> "Op Stk Value : .. Sale Prv Value : .." (klm_stock_sale_prvsa footer)
#   * "value\s*in\s*rs"    -> Marg text-grid per-division "Value in Rs. <nums>" subtotal furniture
_LABEL_TOTAL_RE = re.compile(
    r"\b(?:grand\s*total|group\s*total|sub\s*tot(?:al)?|net\s*(?:total|amount)"
    r"|page\s*total|customer\s*totals?|product\s*sub\s*tot|op\s*stk\s*value"
    r"|sale\s*prv\s*value|value\s*in\s*rs|total)\b",
    re.I,
)
# Marg "Stock Analysis (text)" prints each division block's subtotals as bare
# label rows "Quantity <14 nums>" / "Value in Rs. <7 nums>" — furniture, not a
# product row. Anchored to the leading label so a product literally named
# "Quantity" (none exist) would still need the label to START the line.
_MARG_GRID_FOOTER_RE = re.compile(r"^\s*(?:quantity|value\s*in\s*rs)\b[\s\d.,()-]*$", re.I)
_MF_SUMMARY_RE = re.compile(
    r"^\s*\d+\.\s+(?:invoice|credit\s*note|cash\s*memo|challan|debit\s*note|"
    r"s\.?\s*return|sales\s*return)\b",
    re.I,
)
_BARE_NUMERIC_RE = re.compile(r"^[\s\d.,()*%-]+$")
_FOOTER_PAIR_RE = re.compile(
    r"^\s*(?:opening|closing|purchase|sales|stock|receipt|issue)"
    r"(?:\s+(?:value|qty|stock|return))?\s*[:=]?\s*-?[\d,]+\.?\d*\s*$",
    re.I,
)

# Page furniture / banners / address blocks. Deliberately narrow: every rule
# here removes a line from UNEXPLAINED consideration, so false breadth hides
# real drops. Anything not confidently noise stays data/text and must earn a
# claim instead.
_NOISE_RE = re.compile(
    r"^\s*page\b|\bpage\s*\d+\s*(?:of\s*\d+)?\s*$|\bpage\s*:\s*\d"
    r"|^report\s*date\b|^amount\s*=\s*q|^generated\s*date\b"
    r"|powered\s+by|taken\s+(?:by|at)"
    r"|^gstin\b|^tin\b|^phone\b|^ph\s*[:.]|^e-?mail\b|^mobile\b|^cell\b"
    r"|^d\.?l\.?\s*(?:no|nos)\b|licen[cs]e"
    r"|stock\s*(?:and|&)\s*sales?\s*(?:statement|report|analysis|register)"
    r"|sales?\s*(?:detail|summary)?\s*register|customer.{0,12}itemwise"
    r"|^from\s+date\b|\bfrom\s+date\b.*\bto\b|^from\s*:.*\bto\s*:"
    r"|^from\s+\d{1,2}[/-].*\bto\b\s*:?\s*\d"  # "From 01/05/2026 To 27/05/2026"
    # Report title banners that reprint per page ("Companywise Customerwise
    # Report From date .. to date ..", "... Sales Statement From ..").
    r"|(?:company|customer|item|product|area|group)wise\s+\w*\s*report"
    r"|\breport\s+from\s+date\b"
    # Page footer: "<VENDOR> - dd/mm/yy HH:MM" print timestamp.
    r"|-\s*\d{2}/\d{2}/\d{2,4}\s+\d{1,2}:\d{2}\s*$"
    # Purchase/inward register — a SECOND section some stock reports append
    # ("PURCHASE DETAIL :-", "SUPPLIER NAME", then supplier-invoice lines like
    # "KLM LABORATORIES PVT LTD (HYD) 2627/02212 06-05-2026 05-05-2026 202755.00").
    # These are not product stock rows; the parser correctly ignores them. Match
    # the section header and the supplier-invoice line shape (a manufacturer name
    # followed by an invoice no, two dates and a value).
    r"|^purchase\s*detail\b|^supplier\s*(?:name|detail)\b"
    r"|^printed\s+(?:on|by)\b|^continued\b|\(contd",
    re.I,
)
# A supplier-invoice detail line from the purchase register: <NAME> <inv-no>
# <dd-mm-yyyy> <dd-mm-yyyy> <value>. Distinct from a product row (which has no
# two-date run). Kept separate so it only ever removes these, never a stock row.
_SUPPLIER_INVOICE_RE = re.compile(
    r"^[A-Z].*?\s+\S*\d{3,}\S*\s+\d{2}-\d{2}-\d{4}\s+\d{2}-\d{2}-\d{4}\s+[\d,]+\.\d{2}\s*$"
)

# Column-header vocabulary. A line whose alpha tokens are mostly these words is
# a header row, not data.
_HEADER_VOCAB = frozenset(
    """qty quantity rate amount batch inv invno bill date item product pack
    opening closing sales sale purchase purchases disc discount sch scheme mrp
    free value stock srno sr no particulars name total gst hsn exp expiry mfg
    company division party customer area code desc description balance opening
    ptr pts van unit uom rec recd issued qoh boxes strips fqty netqty amt
    """.split()
)


def _canon_num(tok):
    """Canonical string for a numeric token so row values and line tokens meet:
    '1,584.43'->'1584.43', '10.'->'10', '5.0'->'5', '-999'->'-999'."""
    t = tok.replace(",", "").rstrip(".")
    if not t or t == "-":
        return None
    try:
        return format(round(float(t), 2), "g")
    except ValueError:
        return None


def _distinctive(canon):
    """Anchors allowed to claim a line: decimal-bearing, or >=3 digits, or
    |v| >= 100 — never bare small ints (a qty '10' matches half the file)."""
    if canon is None:
        return False
    if "." in canon:
        return True
    digits = canon.lstrip("-")
    if len(digits) >= 3:
        return True
    try:
        return abs(float(canon)) >= 100
    except ValueError:
        return False


def _norm_text(s):
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def _iter_cells(rows, headers=None):
    for row in rows:
        if isinstance(row, dict):
            for k, v in row.items():
                if not str(k).startswith("_") and v not in (None, ""):
                    yield v
        else:
            for v in row:
                if v not in (None, ""):
                    yield v


# Column names whose text identifies the PARTY/BAND a line belongs to (vs the
# product). Data-shaped party-header lines are corroborated by these texts only;
# letting product texts corroborate them would also corroborate dropped ITEM
# lines (their product name matches a kept row's) and hide row loss.
_PARTY_COLS = frozenset((
    "party name", "party", "customer", "customer name", "cust name", "buyer",
    "account name", "account", "area", "city", "town", "station", "location",
))
_PARTY_KEYS = frozenset((
    "party_name", "party_location", "customer_name", "area", "vendor_name",
))


def _party_col_positions(headers):
    pos = set()
    for i, h in enumerate(headers or []):
        n = re.sub(r"[^a-z ]", "", str(h).lower()).strip()
        if n in _PARTY_COLS:
            pos.add(i)
    return pos


def _is_product_key(key):
    """A dict-row key naming the PRODUCT/item (not party/vendor/boilerplate). Used
    to measure product distinctness for the unique_products discriminator — must
    exclude repeated boilerplate fields (vendor_name, report_type_label,
    division) that would otherwise dominate a row's 'longest text' and collapse
    distinctness to ~0."""
    k = str(key).lower()
    if any(bad in k for bad in ("party", "customer", "vendor", "supplier",
                                "division", "label", "report", "location")):
        return False
    return ("product" in k or "item" in k or "canonical" in k
            or k in ("description", "particulars"))


def _product_col_positions(headers):
    pos = set()
    for i, h in enumerate(headers or []):
        n = str(h).lower()
        if "party" in n or "customer" in n:
            continue
        if "product" in n or "item" in n or n in ("description", "particulars"):
            pos.add(i)
    return pos


def build_row_index(rows, headers=None):
    """Value index over the parser's raw output rows (pre-enrichment).

    nums:       canonical numeric cell values (set — integer-grid claims)
    num_counts: Counter of the same (multiset — decimal consumption claims;
                each row value can explain at most that many lines, so
                duplicate amounts cannot hide extra dropped lines)
    ids:        alnum tokens >=5 chars (batch/invoice/date claims)
    texts:      all normalized text cells >=6 chars (TEXT-line context)
    texts_party: text cells from party/area columns only (data-line context)
    """
    from collections import Counter
    nums, ids, texts, texts_party = set(), set(), [], []
    num_counts = Counter()
    party_pos = _party_col_positions(headers) if headers else None
    prod_pos = _product_col_positions(headers) if headers else None
    rec_with_dec = 0
    prod_heads = set()  # normalized 8-char product-name heads (fast pre-filter)
    row_names = []      # per-row product name (unique_products discriminator)
    for row in rows:
        if isinstance(row, dict):
            items = [(k, v) for k, v in row.items()
                     if not str(k).startswith("_") and v not in (None, "")]
            partyish = lambda key: key in _PARTY_KEYS  # noqa: E731
            productish, restrict = _is_product_key, True
        else:
            items = [(i, v) for i, v in enumerate(row) if v not in (None, "")]
            partyish = (lambda key: party_pos is not None and key in party_pos)
            # LIST rows: use the product column if headers name one; else fall
            # back to the row's longest alpha text (no boilerplate column exists
            # in a positional row, so this is safe).
            productish = (lambda key: prod_pos is not None and key in prod_pos)
            restrict = bool(prod_pos)
        row_has_dec = False
        row_longest = ""
        for key, v in items:
            s = str(v).strip()
            if not s:
                continue
            c = _canon_num(s) if _NUM_RE.fullmatch(s.replace(" ", "")) else None
            if c is not None:
                nums.add(c)
                if _distinctive(c):
                    num_counts[c] += 1
                    if "." in c:
                        row_has_dec = True
                continue
            up = s.upper()
            for tok in _ID_RE.findall(up):
                ids.add(tok)
                digits = re.sub(r"[^0-9]", "", tok)
                if len(digits) >= 5:
                    ids.add(digits)  # date '09-06-26' also as '090626'
            # numbers embedded in text cells still count (e.g. pack '30 GM')
            for n in _NUM_RE.findall(s):
                c2 = _canon_num(n)
                if c2 is not None and _distinctive(c2):
                    nums.add(c2)
            t = _norm_text(s)
            if len(t) >= 6:
                texts.append(t)
                if len(t) >= 8:
                    prod_heads.add(t[:8])
                if partyish(key):
                    texts_party.append(t)
                take = productish(key) if restrict else (
                    sum(ch.isalpha() for ch in s) >= 3)
                if take and len(t) > len(row_longest):
                    row_longest = t
        if row_longest:
            row_names.append(row_longest)
        if row_has_dec:
            rec_with_dec += 1
    n = len(rows) or 1
    # value_bearing: do the records themselves carry per-row money decimals
    # (amounts/values)? If yes (VENUS party register, value-bearing stock), a
    # line whose distinctive DECIMAL is absent from the index is a genuine drop,
    # so claims stay strict (decimal consumption). If no (qty-only stock grids
    # like UMA / marg_movement_detail that omit the value columns), the line's
    # decimals are un-stored value columns — claim on the (unique) product NAME
    # or distinctive integers/ids instead, or every real row looks "unexplained".
    value_bearing = (rec_with_dec / n) >= 0.5
    # unique_products: does the report carry ~one row per distinct product name
    # (a STOCK statement) vs the same product repeated across many parties (a
    # PARTY register)? When unique, a product-NAME claim is safe even as a last
    # resort — a genuinely dropped product has NO record, hence no text, so it
    # still can't be claimed; this rescues zero-movement stock rows (all columns
    # 0/dash, nothing to value-anchor) without hiding drops.
    #   Proxy = distinct FULL row names / rows. The old 8-char-head proxy
    #   COLLIDED same-brand siblings ('EPISERT CREAM 20 GRA'/'10 GRAM' -> both
    #   'EPISERTC'; 'MELBOOST CAPS'/'NXT'/'SOLUTION(B/S)' -> all 'MELBOOST'), so a
    #   legitimate stock statement fell to ~0.73 and the rescue never fired.
    #   Full names measure 0.98 there; a party register (VENUS) stays ~0.20
    #   because products genuinely repeat across parties, so the gate is intact.
    unique_products = (len(set(row_names)) / n) >= 0.8
    return {"nums": nums, "num_counts": num_counts, "ids": ids,
            "texts": texts, "texts_party": texts_party,
            "prod_heads": prod_heads, "value_bearing": value_bearing,
            "unique_products": unique_products}


def classify_line(line):
    """Static taxonomy of a raw text line (no row knowledge):
    'blank' | 'total' | 'noise' | 'data' | 'text'."""
    s = line.strip()
    if not s or _RULE_RE.fullmatch(s):
        return "blank"
    nums = _NUM_RE.findall(s)
    if _MF_SUMMARY_RE.match(s) and len(nums) >= 2:
        return "total"
    if _LABEL_TOTAL_RE.search(s) and nums:
        return "total"
    if _MARG_GRID_FOOTER_RE.match(s):
        return "total"
    if _BARE_NUMERIC_RE.fullmatch(s) and len(nums) >= 3:
        return "total"
    if _FOOTER_PAIR_RE.match(s):
        return "total"
    if _NOISE_RE.search(s) or _SUPPLIER_INVOICE_RE.match(s):
        return "noise"
    alpha = [t.lower() for t in re.findall(r"[A-Za-z]+", s)]
    if alpha:
        hits = sum(1 for t in alpha if t in _HEADER_VOCAB)
        if hits >= 3 and hits * 2 >= len(alpha):
            return "noise"
    has_dec = bool(_DEC_RE.search(s))
    # A product/data row must carry a NAME. A line of only numbers & punctuation
    # (no alpha run) is a per-row subtotal / echo / stray total — never a dropped
    # PRODUCT row — so treat it as furniture. Catches per-bill "qty amount"
    # echoes ("2.00 312.15" printed under each nagammai bill) that would otherwise
    # look unexplained once the bill line above consumed the amount. (>=3 bare
    # nums were already caught as 'total' above; this adds the 2-number case.)
    if not _ALPHA_RUN.search(s):
        return "total" if len(nums) >= 2 else "text"
    if (has_dec and len(nums) >= 2) or (
        len(nums) >= 4 and _ALPHA_RUN.match(s)
    ):
        return "data"
    return "text"


_GRID_TOK_RE = re.compile(r"^-?[\d,]*\d\.?\d*$")  # a pure-numeric grid cell


def _line_product_name_norm(s):
    """The product-name portion of a stock line = the text BEFORE the trailing
    numeric grid (the first run of >=3 consecutive pure-numeric tokens), with
    DIGITS PRESERVED. _norm_text keeps [A-Z0-9], so
    'EKRAN 80 HYDRAGEL SUNSCREEN 50GM 0 0 0 0 0 0.00 348'
    -> name tokens 'EKRAN 80 HYDRAGEL SUNSCREEN 50GM' -> 'EKRAN80HYDRAGELSUNSCREEN50GM'.
    Keeping the digits is what makes sibling strengths/sizes distinct
    ('EKRAN 80' != 'EKRAN 30', 'ZITLIN 250' != 'ZITLIN 500') and lets a name's
    embedded pack/strength still anchor it — the old tokenizer dropped every
    numeric and short token, so it could neither match nor tell siblings apart.
    Pack tokens ('50GM', '10S', '1*10', '30ML') are alphanumeric, not pure
    numeric, so they stay in the name and never start the grid run."""
    toks = s.split()
    cut, run = len(toks), 0
    for i, t in enumerate(toks):
        if _GRID_TOK_RE.match(t):
            run += 1
            if run >= 3:
                cut = i - run + 1
                break
        else:
            run = 0
    return _norm_text(" ".join(toks[:cut]))


def _line_product_claimed(s, index):
    """The line's product-name text matches a record's product/name text by
    prefix-containment (digits preserved). Used ONLY for unique-product
    (stock-statement) layouts, where a name match cannot hide a drop: a
    genuinely dropped product has NO record, hence no text, so its name is a
    prefix of nothing. Prefix (not loose substring) + digit preservation keeps
    it from cross-matching a different sibling, so it is strictly SAFER than the
    old matcher while finally claiming the zero-movement rows (every column
    0/dash + a trailing MRP/rate integer) it used to leave UNEXPLAINED.
    Pre-filtered on the 8-char product-head set."""
    norm = _line_product_name_norm(s)
    if len(norm) < 8 or norm[:8] not in index["prod_heads"]:
        return False
    for t in index["texts"]:
        if len(t) >= 8 and (t.startswith(norm) or norm.startswith(t)):
            return True
    return False


def _line_id_claimed(s, index):
    up = s.upper()
    for tok in _ID_RE.findall(up):
        if tok in index["ids"]:
            return True
        digits = re.sub(r"[^0-9]", "", tok)
        if len(digits) >= 5 and digits in index["ids"]:
            return True
    return False


_VALUE_TOK_RE = re.compile(r"^-?[\d,]*\d\.?\d*$")
_VALUE_GLUE_RE = re.compile(r"^(-?[\d,]*\d\.\d{1,2})(?=[A-Za-z(])")


def _line_value_tokens(s):
    """Distinctive numeric VALUES on the line, as (decimals, integers).

    Whitespace-tokenized so a number glued to a LEADING letter — a batch/invoice
    id like 'AA3602' or 'SZ3881', whose digit run _NUM_RE would otherwise mine as
    a fake amount — is rejected (it starts with a letter). A decimal amount glued
    to a TRAILING name ('9627.10MAUNISH') is still captured via its leading
    decimal. Only these are used to claim, so ids can never masquerade as values.
    """
    decs, ints = [], []
    for tok in s.split():
        if _VALUE_TOK_RE.match(tok):
            c = _canon_num(tok)
        else:
            m = _VALUE_GLUE_RE.match(tok)
            c = _canon_num(m.group(1)) if m else None
        if c is None or not _distinctive(c):
            continue
        # A bare 7+ digit integer (or a scientific-notation canon of one) is a
        # phone / customer code / GSTIN fragment, never a line amount (real
        # amounts are far smaller and carry paise). Excluding it stops a glued
        # salesman phone from posing as an unconsumable value anchor.
        if "e" in c or (("." not in c) and len(c.lstrip("-")) >= 7):
            continue
        (decs if "." in c else ints).append(c)
    return decs, ints


def _line_claimed(s, index):
    """Value-anchored claim. Two modes, chosen per file by index['value_bearing'].

    VALUE-BEARING (records carry per-row money decimals — VENUS register, value
    stock): a decimal-bearing line is claimed ONLY by one of its own distinctive
    decimals via MULTISET CONSUMPTION (ids are NOT enough — dropped continuation
    lines share batch/invoice ids with kept siblings; measured on VENUS pre-fix:
    id-claims hid all 405 drops, amount-consumption exposes them). Each row
    decimal explains at most as many lines as rows carry it, so duplicate prices
    can't hide extra drops.

    QTY-ONLY (records omit the value columns — UMA / marg_movement_detail stock
    grids): the line's decimals are un-stored VALUE columns, so decimal matching
    would flag every real row. Claim instead on the (unique) product NAME, or a
    distinctive integer/id. A genuinely dropped product still has no row → no
    text/values → correctly unexplained; the printed-total reconcile is the
    aggregate backstop.
    """
    decs, ints = _line_value_tokens(s)

    if index.get("value_bearing", True):
        # Consume over ALL distinctive numbers (decimals AND >=3-digit / >=100
        # integers) via the multiset — decimals first (the money identity), then
        # integer amounts. Consumption (not set membership) keeps VENUS honest: a
        # dropped line only claims while its value has surplus supply. Trying the
        # integers too fixes registers whose AMOUNT prints as a bare integer
        # (party_item_summary "EKRAN SOFT 1 - 795 795 0.08" — the 0.08 ratio must
        # not early-return before the 795 amount is checked). A dropped VENUS line
        # has only small non-distinctive qtys besides its (absent) amount, so it
        # still cannot claim.
        anchors = decs + ints
        if anchors:
            counts = index["num_counts"]
            for c in anchors:
                if counts.get(c, 0) > 0:
                    counts[c] -= 1
                    return True
            # Unconsumed. If the line carries a real DECIMAL value (a paise amount),
            # it is a real-drop candidate — NO name rescue (this is what keeps the
            # VENUS dropped-amount and the duplicate-amount cases honest). If its
            # only anchors are INTEGERS (an MRP / item code / stray qty on an
            # otherwise zero-movement stock row), a UNIQUE-product report claims it
            # by name — a genuinely dropped product has no record, hence no text.
            if (not decs and index.get("unique_products")
                    and _line_product_claimed(s, index)):
                return True
            return False
        # NO distinctive anchor at all (a zero-movement stock row: every column
        # 0/dash). Nothing to value-anchor, so a unique-product report claims it
        # by name (a truly dropped product has no record/text -> still unclaimed).
        if index.get("unique_products") and _line_product_claimed(s, index):
            return True
        return _line_id_claimed(s, index)

    # qty-only mode
    if _line_product_claimed(s, index):
        return True
    if (decs or ints) and any(c in index["nums"] for c in (decs + ints)):
        return True
    return _line_id_claimed(s, index)


def _context_claimed(s, index, _memo=None, key="texts"):
    norm = _norm_text(re.sub(r"[-\s\d.,()]+$", "", s))
    if len(norm) < 6:
        return False
    if _memo is not None and norm in _memo:
        return _memo[norm]
    hit = False
    for t in index[key]:
        if norm in t or t in norm:
            hit = True
            break
    if _memo is not None:
        _memo[norm] = hit
    return hit


def _empty(applicable=False, reason=""):
    return {
        "version": LEDGER_VERSION,
        "applicable": applicable,
        "capped": False,
        "reason": reason,
        "counts": {},
        "unexplained_ratio": 0.0,
        "unexplained_sample": [],
        "rows_unclaimed": 0,
    }


def audit_text_lines(raw_text, rows, headers=None, *, caps=CAPS):
    """PDF entry point. Classify every non-blank line of ``raw_text`` against the
    parser's raw output ``rows`` (list-of-lists or list-of-dicts)."""
    import time
    t0 = time.perf_counter()
    if not raw_text or rows is None:
        return _empty(reason="no raw_text or rows")
    lines = raw_text.splitlines()
    if len(lines) > caps["max_lines"] or len(rows) > caps["max_rows"]:
        out = _empty(reason="capped")
        out["capped"] = True
        return out
    if not rows:
        return _empty(reason="zero rows (layout detection owns this)")

    index = build_row_index(rows, headers)
    counts = {"lines": 0, "noise": 0, "total": 0, "context": 0,
              "context_unclaimed": 0, "data": 0, "claimed": 0, "unexplained": 0}
    samples = []
    memo = {}
    memo_party = {}
    party_heads = {t[:8] for t in index["texts_party"]}
    line_nums = set()

    # Whole-document PAGE REPETITION: some vendors' extracted PDF text repeats the
    # ENTIRE report once per printed page (manufacturerwise_billwise: 10 identical
    # pages). The parser emits ONE copy, so the ledger would count the other 9 as
    # unexplained "drops". Detect it as heavy EXACT-line duplication at scale and
    # audit only the FIRST occurrence of each line. Scoped tightly so it can never
    # hide a real duplicate-row drop: that case is a handful of lines (no page
    # structure) and misses the scale+ratio bar; and a genuinely dropped line
    # still survives dedup as one distinct, unclaimed line. Real transactions are
    # never exact-duplicate (invoice no / date differ), so ~40%+ identical lines
    # at scale only occurs with structural repetition.
    _stripped = [s for s in (ln.strip() for ln in lines)
                 if s and not _RULE_RE.fullmatch(s)]
    page_repeated = (len(_stripped) >= 60
                     and len(set(_stripped)) <= 0.6 * len(_stripped))
    seen_lines = set()

    for line in lines:
        for n in _NUM_RE.findall(line):
            c = _canon_num(n)
            if c is not None and _distinctive(c):
                line_nums.add(c)
        kind = classify_line(line)
        if kind == "blank":
            continue
        if page_repeated:
            _k = line.strip()
            if _k in seen_lines:
                continue
            seen_lines.add(_k)
        counts["lines"] += 1
        if kind in ("noise", "total"):
            counts[kind] += 1
            continue
        if kind == "data":
            counts["data"] += 1
            # Party-header corroboration runs FIRST so a data-shaped header does
            # not consume an item row's amount slot. Only party/area texts.
            head = _norm_text(line.strip()[:14])[:8]
            if head in party_heads and _context_claimed(
                line, index, memo_party, key="texts_party"
            ):
                counts["claimed"] += 1
            elif _line_claimed(line, index):
                counts["claimed"] += 1
            else:
                counts["unexplained"] += 1
                if len(samples) < caps["sample"]:
                    samples.append(line.strip()[:120])
            continue
        # text-only
        if _context_claimed(line, index, memo) or _line_claimed(line, index):
            counts["context"] += 1
        else:
            counts["context_unclaimed"] += 1

    # PIVOTED / transposed layouts (prompt_datewise_favourite): the raw text has
    # few "data" lines but the parser expands a grid into many rows (rows >> data
    # lines). The ledger's line-per-row model does not fit — a handful of pivot
    # lines can never account for hundreds of rows — so it must not fire. Mark
    # inapplicable rather than emit a meaningless unexplained count.
    if counts["data"] and len(rows) > 2.5 * counts["data"]:
        out = _empty(reason="pivoted layout (rows >> data lines)")
        out["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        return out

    # reverse direction (informational): rows whose distinctive values appear in
    # NO input line. O(rows) via the line_nums set built in the pass above.
    rows_unclaimed = 0
    for row in rows[: caps["max_rows"]]:
        vals = list(_iter_cells([row]))
        distinct = []
        for v in vals:
            s = str(v).strip()
            if _NUM_RE.fullmatch(s.replace(" ", "")):
                c = _canon_num(s)
                if c is not None and _distinctive(c):
                    distinct.append(c)
        if distinct and not any(c in line_nums for c in distinct):
            rows_unclaimed += 1

    data = counts["data"]
    return {
        "version": LEDGER_VERSION,
        "applicable": True,
        "capped": False,
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        "counts": counts,
        "unexplained_ratio": round(counts["unexplained"] / data, 4) if data else 0.0,
        "unexplained_sample": samples,
        "rows_unclaimed": rows_unclaimed,
    }


def audit_sheet_rows(sheets, records, *, caps=CAPS):
    """XLSX entry point. ``sheets`` = [(sheet_name, srows)] with srows the raw
    list-of-lists; ``records`` = the parser's emitted records (pre-cast).
    Classifies every input sheet row: emitted / header-noise / total / context /
    unexplained. Immune to the raw_text preview truncation because it runs on
    the full srows inside the pipeline."""
    import time
    t0 = time.perf_counter()
    if not sheets or records is None:
        return _empty(reason="no sheets or records")
    total_rows = sum(len(srows) for _, srows in sheets)
    if total_rows > caps["max_lines"] or len(records) > caps["max_rows"]:
        out = _empty(reason="capped")
        out["capped"] = True
        return out
    if not records:
        return _empty(reason="zero records (layout detection owns this)")

    index = build_row_index(records)
    counts = {"lines": 0, "noise": 0, "total": 0, "context": 0,
              "context_unclaimed": 0, "data": 0, "claimed": 0, "unexplained": 0}
    samples = []
    per_sheet = []
    memo = {}
    memo_party = {}
    for name, srows in sheets:
        sc = {"sheet": str(name), "rows": 0, "claimed": 0, "unexplained": 0}
        for srow in srows:
            cells = [c for c in (srow or []) if c not in (None, "")]
            if not cells:
                continue
            counts["lines"] += 1
            sc["rows"] += 1
            pseudo = " ".join(str(c) for c in cells)
            kind = classify_line(pseudo)
            if kind == "blank":
                continue
            if kind in ("noise", "total"):
                counts[kind] += 1
                continue
            if kind == "data":
                counts["data"] += 1
                # same ordering rationale as audit_text_lines: band/party rows
                # corroborate via party texts and must not consume amount slots
                if _context_claimed(pseudo, index, memo_party, key="texts_party"):
                    counts["claimed"] += 1
                    sc["claimed"] += 1
                elif _line_claimed(pseudo, index):
                    counts["claimed"] += 1
                    sc["claimed"] += 1
                else:
                    counts["unexplained"] += 1
                    sc["unexplained"] += 1
                    if len(samples) < caps["sample"]:
                        samples.append(f"[{name}] {pseudo.strip()[:110]}")
                continue
            if _context_claimed(pseudo, index, memo) or _line_claimed(pseudo, index):
                counts["context"] += 1
            else:
                counts["context_unclaimed"] += 1
        per_sheet.append(sc)

    # PIVOTED / transposed layouts (areacity_wise_sale_pivot): the sheet has few
    # data rows but the parser un-pivots a grid into many records (records >> data
    # rows). The line-per-row model does not fit, so the ledger must not fire —
    # same guard as audit_text_lines.
    if counts["data"] and len(records) > 2.5 * counts["data"]:
        out = _empty(reason="pivoted layout (records >> data rows)")
        out["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        return out

    data = counts["data"]
    return {
        "version": LEDGER_VERSION,
        "applicable": True,
        "capped": False,
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        "counts": counts,
        "unexplained_ratio": round(counts["unexplained"] / data, 4) if data else 0.0,
        "unexplained_sample": samples,
        "rows_unclaimed": 0,
        "per_sheet": per_sheet,
    }
