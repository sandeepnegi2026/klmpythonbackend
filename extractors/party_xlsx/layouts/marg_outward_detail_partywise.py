"""
Marg "Outward Detail(s)" party-wise sale export (SATARA PHARMA / KLM COSMO-DERMA-DERMACOR):
a flat per-row table

    Inv No | Inv Date | Qty | Free | BatchNo | Product Name | Sch Amt | Ledger Account |
    MRP | Supplier Name | HSN | Rate | City | PinCode | Manufacturer / Division |
    Parent Manufacturer | Sch% | SchPer | PTR | NSR | TNSR | Address1 | Address2 |
    DLNo | Mode | GrsAmt

The customer sits in the "Ledger Account" column (party_name) and the sale figures map
cleanly, so the generic ``tabular`` reader already extracts the columns correctly. This
layout reuses tabular's exact column mapping and fixes the two Marg-specific quirks that
make ``tabular`` mis-count / mis-name:

  1. Two trailing footer NOISE rows that carry no total label so the tabular guards keep
     them: a firm/phone line ("Medica Ultimate (+91-022-4747-4747)" ... "For Satara Pharma")
     and the record-count line ("(Report End) (N Records)" ... "Authorised Signatory"). Both
     land in the Inv-No column, inherit the previous customer via carry-down and ship as
     phantom sales (the AMBER CONSTANT_COLUMN signal on the 2-row DERMA file, and 9 rows vs
     the printed "7 Records" on COSMO).

  2. The Product Name cell is PRINTED ONLY on the first line of each batch group; the
     following same-batch rows leave it blank (COSMO: 6 of 7 rows blank, all batch CB504 =
     KOJITIN GEL CREAM). ``tabular`` keeps those rows (they carry Inv No/Qty/GrsAmt) but with
     an empty product_name, which is what drives the LOW_MASTER_MATCH bucket. We forward-fill
     product_name from the previous row while the BatchNo is unchanged, so every sale line
     carries its product and can master-match.

Title-gated on the compact "outwarddetail" token (unique across the party_xlsx corpus) PLUS
a columnar Ledger-Account/Product/Qty header, so it claims only this Marg "Outward Detail(s)"
family; every other tabular file is untouched.
"""
from core.header_match import map_headers

from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.layouts.tabular import records_from_mapped
from extractors.party_xlsx.parse_common import cell_text, compact

_TITLE = "outwarddetail"

# Footer noise: a firm phone-number line and the "(Report End) (N Records)" line. Both are
# emitted by Marg after the TOTAL row; neither is a total label, so tabular can't drop them.
# Matched on the invoice_number cell (where the text lands) with corpus-unique substrings.
_FOOTER_INV_TOKENS = ("report end", "(+91")


def _is_footer_noise(record):
    inv = str(record.get("invoice_number", "")).strip().lower()
    if not inv:
        return False
    return any(tok in inv for tok in _FOOTER_INV_TOKENS)


def detect(rows):
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:8]))
    if _TITLE not in head:
        return False
    header_idx = detect_header_row(rows)
    if header_idx is None:
        return False
    keys = {info["canonical"]
            for info in map_headers([str(c) for c in rows[header_idx]], "party").values()}
    return "party_name" in keys and "product_name" in keys and bool(keys & {"amount", "qty"})


def parse_marg_outward_detail_partywise(rows):
    header_idx = detect_header_row(rows)
    if header_idx is None:
        return [], {}
    headers = [str(h) if h else f"col_{i}" for i, h in enumerate(rows[header_idx])]
    records, detected = records_from_mapped(headers, rows, header_idx)

    # (1) Drop the two footer noise rows tabular could not identify.
    records = [r for r in records if not _is_footer_noise(r)]

    # (2) Forward-fill Product Name across a same-batch group (Marg prints it once).
    last_product = ""
    last_batch = ""
    for record in records:
        product = str(record.get("product_name", "")).strip()
        batch = str(record.get("batch_no", "")).strip()
        if product:
            last_product = product
            last_batch = batch
        elif last_product and batch and batch == last_batch:
            record["product_name"] = last_product
    return records, detected
