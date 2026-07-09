from extractors.stock_pdf.parse_common import _clean_number_token, _is_num, _to_number


def _num(v):
    return _to_number(_clean_number_token(v)) or 0.0


def parse_toreo_stock(text):
    """
    Toreo LTD / Sangli Medical ERP Stock Statement (Medica Ultimate).
    Headers: PRODUCT DESCRIPTION PACKING OPSTK PURCH SALE SALE VAL IN/OTSTOCK STK VAL FEB JAN...
    Columns:  0 OPSTK  1 PURCH  2 SALE  3 SALE VAL  4 IN/OT  5 STOCK(closing)  6 STK VAL  (FEB/JAN ignored)

    Medica Ultimate prints a diagonal watermark whose single letters bleed into the
    number columns ('0a0'->'00', 'e0'->'0'); left unhandled they read as alpha tokens
    and truncate the numeric tail, dropping the row. We walk the tail from the RIGHT,
    cleaning each glyph-number, and stop at the first genuine non-number (the pack
    unit / product word), so a name digit like 'D3' in 'KLM D3 60K' is never eaten.
    """
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        low = line.lower()
        if "description" in low and "packing" in low and "opstk" in low:
            continue
        if "stockstatement" in low or "sangli medical" in low or "chintamani" in low:
            continue
        if "gstin" in low or "email" in low or "from date" in low:
            continue

        tokens = line.split()
        if len(tokens) < 7:
            continue

        # collect the trailing numeric run (glyph-tolerant), stopping at the pack unit
        i = len(tokens) - 1
        vals = []
        while i >= 0 and _is_num(_clean_number_token(tokens[i])):
            vals.insert(0, _num(tokens[i]))
            i -= 1
        if i < 0 or len(vals) < 7:
            continue

        prod_pack = " ".join(tokens[: i + 1])
        records.append({
            "product_name": prod_pack,
            "opening_stock": vals[0],
            "purchase_stock": vals[1],
            "sales_qty": vals[2],
            "closing_stock": vals[5],
            "closing_stock_value": vals[6],
        })

    return records
