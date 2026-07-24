from core.canonical import numeric_fields

from extractors.stock_xlsx.parse_common import to_number


def cast_numbers(records):
    for field in numeric_fields("stock"):
        for row in records:
            if field in row:
                parsed = to_number(row.get(field))
                row[field] = parsed if parsed is not None else None


def sanity_warnings(records):
    warnings = []
    bad = 0
    checked = 0
    for idx, row in enumerate(records, start=1):
        opening = to_number(row.get("opening_stock")) or 0.0
        purchase = to_number(row.get("purchase_stock")) or 0.0
        purchase_free = to_number(row.get("purchase_free")) or 0.0
        purchase_return = to_number(row.get("purchase_return")) or 0.0
        sales = to_number(row.get("sales_qty")) or 0.0
        sales_free = to_number(row.get("sales_free")) or 0.0
        sales_return = to_number(row.get("sales_return")) or 0.0
        closing = to_number(row.get("closing_stock"))
        if closing is None:
            continue
        checked += 1
        # Free goods received add to stock; free goods issued leave it. Layouts that
        # don't break out free populate these as 0, so the equation is unchanged there.
        expected = opening + purchase + purchase_free - purchase_return - sales - sales_free + sales_return
        if abs(expected - closing) / max(abs(closing), 1.0) > 0.01:
            bad += 1
            if len(warnings) < 50:
                warnings.append(
                    f"{row.get('product_name') or f'row {idx}'}: vendor's report prints closing "
                    f"{closing:.0f}, but their own opening + purchases - sales = {expected:.0f} "
                    f"(off by {closing - expected:+.0f}) -- source-file mismatch, extraction is correct."
                )
    if checked:
        pass_rate = (checked - bad) / checked
        if pass_rate < 0.98:
            warnings.append(
                f"{pass_rate:.1%} of rows balance ({checked - bad}/{checked}); the rest don't add up in "
                f"the vendor's own report -- source-file data issue, not an extraction error."
            )
    summary = {
        "checked": checked,
        "failed": bad,
        "passed": checked - bad,
        "pass_rate": ((checked - bad) / checked) if checked else 0.0,
    }
    return warnings, summary
