"""
Siva Software Consultant stock report layout.

Header line:
  S.No  Product Name  Packing  Opening  Purchas  Sales  c_stock  Expiry  Pr_sale

Product name may wrap to the line *before* the data row (prefix),
or *after* the data row (suffix, e.g. "SPF30" after EKRAN AQUA GEL).

We use look-ahead: a non-data text line is a PREFIX for the next row
only if the next data row's inline text looks like just a packing token.
Otherwise it is a SUFFIX for the previous row.
"""
import re

from extractors.stock_pdf.parse_common import _skip_line


_HEADER_RE = re.compile(
    r"s\.?no\s+product\s+name\s+packing\s+opening\s+purchas",
    re.I,
)

_SERNO_RE = re.compile(r"^(\d{1,4})\s+(.+)$")

_EXP_RE = re.compile(r"\d{1,2}-\d{4}")

_TOTAL_RE = re.compile(r"^\s*(total|powered by|page \d)", re.I)

_PACK_ONLY_RE = re.compile(
    r"^(?:\d+(?:\.\d+)?\s*)?(?:GM|GMS|ML|MG|TAB|CAP|CREAM|LOTION|BAR|'S|PCS|SACHET|OINT|SERUM)$",
    re.I,
)


def _parse_data_line(rest):
    """Parse the portion after the serial number.
    Returns (inline_text, pack, nums, expiry)."""
    tokens = rest.split()
    nums = []
    expiry = ""
    while tokens:
        t = tokens[-1]
        cleaned = t.rstrip(".").replace(",", "")
        try:
            float(cleaned)
            nums.insert(0, float(cleaned))
            tokens.pop()
            continue
        except ValueError:
            pass
        if _EXP_RE.match(t):
            expiry = t
            tokens.pop()
            continue
        break

    inline_text = " ".join(tokens)

    # Separate packing from inline text
    pack = ""
    name_tokens = inline_text.split()
    if len(name_tokens) > 1:
        last = name_tokens[-1]
        if _PACK_ONLY_RE.match(last):
            pack = last
            name_tokens = name_tokens[:-1]
    elif len(name_tokens) == 1 and _PACK_ONLY_RE.match(name_tokens[0]):
        pack = name_tokens[0]
        name_tokens = []

    product_text = " ".join(name_tokens)
    return product_text, pack, nums, expiry


def parse_siva_stock(text):
    """Parse Siva Software Consultant stock report."""
    records = []
    lines = text.splitlines()
    in_data = False
    pending_text = ""  # accumulated non-data text between data rows

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue

        # Detect header line — start parsing after it
        if _HEADER_RE.search(line):
            in_data = True
            pending_text = ""
            continue

        if not in_data:
            continue

        # Stop at totals / footer
        if _TOTAL_RE.match(line):
            # Any pending text is a suffix for the last record
            if pending_text and records:
                records[-1]["product_name"] += " " + pending_text
                pending_text = ""
            # A mid-file footer (per-page "Total :" / "Powered by" / "Page N") must
            # NOT abort the whole parse, or every data row on later pages is dropped.
            # This branch is checked BEFORE _SERNO_RE below, so the footer line itself
            # is still fully rejected (never emitted as a data row); skip only it.
            continue

        m = _SERNO_RE.match(line)
        if m:
            # This is a data row starting with S.No
            rest = m.group(2).strip()
            product_text, pack, nums, expiry = _parse_data_line(rest)

            if len(nums) < 4:
                continue

            # Decide if pending_text is a prefix for THIS row or suffix for PREVIOUS
            if pending_text:
                if not product_text or _PACK_ONLY_RE.match(product_text):
                    # This row has no product text (only packing) → pending is PREFIX
                    full_name = pending_text
                    if product_text and not pack:
                        pack = product_text
                else:
                    # This row has its own product text → pending is SUFFIX for previous
                    if records:
                        records[-1]["product_name"] += " " + pending_text
                    full_name = product_text
                pending_text = ""
            else:
                full_name = product_text

            r = {
                "product_name": full_name,
                "pack": pack,
                "opening_stock": nums[0],
                "purchase_stock": nums[1],
                "sales_qty": nums[2],
                "closing_stock": nums[3],
            }
            if expiry:
                r["expiry"] = expiry
            if len(nums) >= 5:
                r["previous_sale"] = nums[4]
            records.append(r)
        else:
            # Non-data line — accumulate for later decision
            if not _skip_line(line) and not _TOTAL_RE.match(line):
                if pending_text:
                    pending_text += " " + line
                else:
                    pending_text = line

    # Handle trailing pending_text as suffix for last record
    if pending_text and records:
        records[-1]["product_name"] += " " + pending_text

    return records
