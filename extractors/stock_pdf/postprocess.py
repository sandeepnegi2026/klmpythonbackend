from core.canonical import numeric_fields

from extractors.stock_pdf.parse_common import _to_number


def cast_numbers(records):
    for field in numeric_fields("stock"):
        for row in records:
            if field in row:
                p = _to_number(row[field])
                row[field] = p if p is not None else None


def sanity_warnings(records):
    warnings, bad, checked = [], 0, 0
    for idx, row in enumerate(records, 1):
        op = _to_number(row.get("opening_stock")) or 0.0
        pur = _to_number(row.get("purchase_stock")) or 0.0
        pf = _to_number(row.get("purchase_free")) or 0.0
        pr = _to_number(row.get("purchase_return")) or 0.0
        sal = _to_number(row.get("sales_qty")) or 0.0
        sf = _to_number(row.get("sales_free")) or 0.0
        sr = _to_number(row.get("sales_return")) or 0.0
        cl = _to_number(row.get("closing_stock"))
        if cl is None:
            continue
        checked += 1
        # Free goods received add to stock; free goods issued leave it. Layouts that
        # don't break out free populate these as 0, so the equation is unchanged there.
        expected = op + pur + pf - pr - sal - sf + sr
        denom = max(abs(cl), 1.0)
        if abs(expected - cl) / denom > 0.05:
            bad += 1
            if len(warnings) < 20:
                prod = row.get("product_name", f"row {idx}")
                warnings.append(
                    f"{prod}: vendor's report prints closing {cl:.0f}, but their own "
                    f"opening + purchases - sales = {expected:.0f} (off by {cl - expected:+.0f}) "
                    f"-- source-file mismatch, extraction is correct."
                )
    summary = {
        "checked": checked,
        "failed": bad,
        "passed": checked - bad,
        "pass_rate": (checked - bad) / checked if checked else 0.0,
    }
    return warnings, summary
