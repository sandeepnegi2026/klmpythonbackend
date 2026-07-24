import re

from core.header_match import normalize

from extractors.party_xlsx.parse_common import (
    cell_text,
    is_numeric_qty,
    is_subtotal,
    split_party_area,
)


def parse_marg_busy(rows):
    header_idx = None
    for idx, row in enumerate(rows[:150]):
        for cell in row:
            norm = normalize(cell)
            if norm in {"qty", "qty."} or norm.startswith("qty"):
                header_idx = idx
                break
        if header_idx is not None:
            break
    if header_idx is None:
        for idx, row in enumerate(rows[:150]):
            joined = normalize(" ".join(row)).replace(" ", "")
            if "description" in joined or "particulars" in joined:
                header_idx = idx
                break
    if header_idx is None:
        return [], {}

    header_row = rows[header_idx]
    qty_col = next((i for i, c in enumerate(header_row) if "qty" in normalize(c)), 1)
    free_col = next((i for i, c in enumerate(header_row) if "free" in normalize(c)), 2)
    rate_col = next((i for i, c in enumerate(header_row) if "rate" in normalize(c)), 3)
    amount_col = next(
        (i for i, c in enumerate(header_row) if "amount" in normalize(c)), 4
    )
    # A "Packg." column sitting BEFORE Qty (SAI PHARMA "Item Name | Packg. | Qty | …") would
    # otherwise be grabbed as the product by the positional pre-qty heuristic below (product
    # <- "60ML"). Detect it so it is excluded from the product candidates and surfaced as pack.
    # None (the common case, no pack column) leaves every other marg_busy file untouched.
    pack_col = next(
        (i for i, c in enumerate(header_row)
         if i < qty_col and normalize(c).replace(".", "").replace(" ", "") in {"pack", "packg", "packing", "size", "uom"}),
        None,
    )

    # ── Page-break noise guard (additive, gated) ──
    # Marg "PARTY / ITEM WISE SALES SUMMARY" exports (YUVEE ENTERPRISE) reprint,
    # at every page break, the company-name masthead band, the report title
    # ("PARTY / ITEM WISE SALES SUMMARY ... Page No..N") and the spaced
    # "D E S C R I P T I O N" column header.  Each of those lines would
    # otherwise be mistaken for a party heading and steal the items that
    # continue after the break.  The guard is engaged ONLY when the original
    # header block itself carries the spaced DESCRIPTION cell (this export
    # family); other marg_busy files (e.g. "Item Name | Packg. | Qty") never
    # build the set, so their output stays byte-identical.
    def _norm_nospace(text):
        return normalize(text).replace(" ", "")

    _desc_header = any(
        _norm_nospace(c) == "description"
        for r in rows[max(0, header_idx - 2) : header_idx + 1]
        for c in r
    )
    _masthead_norms = set()
    if _desc_header:
        for _mast_row in rows[:header_idx]:
            for _mast_cell in _mast_row:
                _mast_norm = normalize(cell_text(_mast_cell))
                if _mast_norm:
                    _masthead_norms.add(_mast_norm)

    def _is_pagebreak_noise(text):
        if not _desc_header:
            return False
        if _norm_nospace(text) == "description":
            return True
        norm = normalize(text)
        if not norm:
            return False
        if norm in _masthead_norms:
            return True
        # The title reprint is re-split across cells at the break ("PARTY /
        # ITEM WISE SALES SUMMARY" | "FROM" | ...), so a long prefix of a
        # masthead line is page-break noise too.
        return len(norm) >= 12 and any(m.startswith(norm) for m in _masthead_norms)

    records = []
    current_party = ""
    for raw_row in rows[header_idx + 1 :]:
        cells = raw_row + [""] * (max(qty_col, amount_col) + 2)
        qty = cell_text(cells[qty_col] if qty_col < len(cells) else "")
        # A qty printed with a thousands separator ("1,234") coerces to NaN in the
        # shared is_numeric_qty test, so the line would fall through to the party-band
        # branch and its product text would overwrite current_party. Strip the grouping
        # ONLY when the cell is a pure grouped-comma integer; comma-less values,
        # decimals, party names and "Total" labels never match, so output is
        # byte-identical (module-local; no shared code touched).
        if re.fullmatch(r"\d{1,3}(?:,\d{3})+", qty):
            qty = qty.replace(",", "")
        # Exclude a leading Packg column so it is not mistaken for the product/party.
        pre_qty = [cell_text(cells[i]) for i in range(min(qty_col, len(cells))) if i != pack_col]
        pre_nonempty = [text for text in pre_qty if text]
        unique_cells = {cell_text(c) for c in cells if cell_text(c)}
        if not is_numeric_qty(qty):
            candidate = pre_nonempty[0] if pre_nonempty else ""
            # Skip pure-decoration lines (a "*****" underline the vendor prints beneath each
            # party name, or "====" / "----" rules): no alphanumeric means it can never be a
            # party — without this the "*****" line OVERWRITES the real party set just above it.
            if candidate and not re.search(r"[A-Za-z0-9]", candidate):
                continue
            # Skip page-break masthead/header reprints WITHOUT touching
            # current_party, so items continuing after the break stay attached
            # to the party that was active before it.
            if candidate and _is_pagebreak_noise(candidate):
                continue
            if len(unique_cells) == 1 and candidate:
                current_party = candidate
            elif candidate and not is_subtotal(candidate):
                current_party = candidate
            continue
        product = (
            pre_nonempty[0]
            if len(pre_nonempty) == 1
            else (pre_nonempty[-1] if pre_nonempty else "")
        )
        if is_subtotal(product):
            continue
        if not current_party or not product:
            continue
        party_name, party_area = split_party_area(current_party)
        records.append(
            {
                "party_name": party_name,
                "party_location": party_area,
                "product_name": product,
                "pack": cell_text(cells[pack_col]) if pack_col is not None and pack_col < len(cells) else "",
                "qty": qty,
                "free_qty": cell_text(cells[free_col]) if free_col < len(cells) else "",
                "rate": cell_text(cells[rate_col]) if rate_col < len(cells) else "",
                "amount": cell_text(cells[amount_col]) if amount_col < len(cells) else "",
            }
        )
    detected = {
        "D E S C R I P T I O N": "product_name",
        "QTY.": "qty",
        "FREE": "free_qty",
        "RATE": "rate",
        "AMOUNT": "amount",
    }
    return records, detected
