import re

from extractors.party_pdf.party_area import extract_party_and_area


# RATHNA rich WEP variant: product-level invoice rows carrying decimal qty and a mid-row
# date + invoice number: "129292 ZITLIN SYRUP 30ML 30 ML 20.000 8.000 1744.06 17/Jun/2026
# RS004353 1661.00 ...". code + name/pack + qty + free + amount + date + invno + goodsvalue.
_RICH_ROW = re.compile(
    r"^(\d{4,6})\s+(.+?)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+"
    r"(\d{2}/[A-Za-z]{3}/\d{4})\s+(\S+)\s+(-?[\d.]+)"
)


def parse_wep_legacy(text):
    text = re.sub(r"\(cid:\d+\)", "", text)
    H = [
        "Party Name",
        "Area",
        "Product Code",
        "Product Name",
        "Qty",
        "Free Qty",
        "Goods Value",
        "PRate",
        "Value(PRate)",
    ]
    _c = text.lower().replace(" ", "")
    if "invdate" in _c and "invnowithprefix" in _c:
        return _parse_wep_rich(text, H)
    pat = re.compile(
        r"^(\d+)\s+(.+?)\s+(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$"
    )
    rows, cur_raw = [], ""
    for line in text.split("\n"):
        s = line.strip().rstrip("*'").strip()
        cm = re.match(r"^CUSTOMER NAME\s*:\s*(.+)", s)
        if cm:
            cur_raw = cm.group(1).strip()
            continue
        m = pat.match(s)
        if m:
            name, area = extract_party_and_area(cur_raw, "wep_legacy")
            rows.append(
                [
                    name,
                    area,
                    m.group(1),
                    m.group(2).strip(),
                    m.group(3),
                    m.group(4),
                    m.group(5),
                    m.group(6),
                    m.group(7),
                ]
            )
    return H, rows


def _parse_wep_rich(text, H):
    """RATHNA product-level WEP variant (decimal qty + mid-row date/invno)."""
    # This variant's _RICH_ROW already CAPTURES the invoice date (group 6) and invoice
    # number (group 7); the original builder discarded both, so a customer who reorders
    # the same product with identical qty/free/amount on several June invoices collapsed
    # into byte-identical rows (false DUPLICATE_ROWS). Emit the two captured fields —
    # "Invoice Date"/"Invoice No" exact-map to invoice_date/invoice_number (no new
    # synonyms) — so each invoice line stays distinct. Extended header is local to this
    # variant; the plain WEP path is untouched.
    H2 = H + ["Invoice Date", "Invoice No"]
    rows, cur_raw = [], ""
    for line in text.split("\n"):
        s = line.strip().rstrip("*'").strip()
        cm = re.match(r"^CUSTOMER NAME\s*:\s*(.+)", s)
        if cm:
            cur_raw = cm.group(1).strip()
            continue
        low = s.lower()
        if low.startswith(("group total", "net total", "grand total")):
            continue
        m = _RICH_ROW.match(s)
        if not m:
            continue
        name, area = extract_party_and_area(cur_raw, "wep_legacy")
        # Goods Value slot carries the AMOUNT (gross sale, reconciles to NET TOTAL);
        # PRate slot holds the printed Goods Value; qty/free are decimals.
        rows.append(
            [
                name,
                area,
                m.group(1),               # Product Code
                m.group(2).strip(),       # Product Name (+pack)
                m.group(3),               # Qty
                m.group(4),               # Free Qty
                m.group(5),               # Goods Value <- Amount (canonical amount)
                "",                       # PRate
                m.group(8),               # Value(PRate) <- printed Goods Value
                m.group(6),               # Invoice Date (dd/Mon/yyyy)
                m.group(7),               # Invoice No (RS004353)
            ]
        )
    return H2, rows
