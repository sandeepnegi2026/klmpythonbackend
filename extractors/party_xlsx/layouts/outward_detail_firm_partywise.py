"""
Marg "Outward Detail(s)" firm-level sale export (DEEPALI DRUG DISTRIBUTORS / KLM) — the
NO-CUSTOMER-COLUMN sibling of ``marg_outward_detail_partywise`` (SATARA PHARMA).

A flat per-row table headed

    InvDate | InvNo | ExpDate | DLNo | PinCode | Product Name | BatchNo | Qty | Free |
    WP% | Sch% | GP% | NSR | Taxable | Area | City | TD% | PCode | Packing | Rate | MRP |
    PTR | PTS | CCode | Nick | Manufacturer / Division | NPR | State | TradeMode

Unlike the SATARA "Outward Detail(s)" export (which carries the customer in a *Ledger
Account* column), this variant has NO customer/ledger column at all — it is the reporting
distributor's own outward sale register, so the party is the FIRM itself, printed only in
the header banner (row 0, e.g. "DEEPALI DRUG DISTRIBUTORS PVT LTD" and echoed in the
"For <firm>" trailer). ``tabular`` maps every product/qty/free/taxable column correctly and
already drops the TOTAL row + the two Marg trailer rows ("Medica Ultimate (+91-...)",
"(Report End) (N Records)"), but leaves ``party_name`` blank on EVERY row -> RED (party
reports require a party_name; see core/triage HARD_REQUIRED_DATA).

This layout reuses tabular's exact column mapping (so qty/free/taxable stay split — no value
column is ever turned into a quantity) and only stamps the firm name into party_name on every
sale line, so the report reconciles as a single-party outward register.

Gate: the compact "outwarddetail" title token PLUS the exact header column RUN of this variant
("InvDate InvNo ExpDate DLNo PinCode Product Name BatchNo Qty Free WP% ...", compacted to
``invnoexpdatedlnopincodeproductnamebatchnoqtyfreewp``). That run is unique to this export —
the SATARA sibling's header is a different column order (Inv No | Inv Date | Qty | Free |
BatchNo | Product Name | ... | Ledger Account), so the two never collide, and no other corpus
file carries it. Checked AFTER marg_outward_detail_partywise (which needs a party_name column
this file lacks), so that sibling is untouched.
"""
from extractors.party_xlsx.header_detect import detect_header_row
from extractors.party_xlsx.layouts.tabular import records_from_mapped
from extractors.party_xlsx.parse_common import cell_text, compact

_TITLE = "outwarddetail"
# The compact header-column run unique to this DEEPALI variant (Inv No -> WP%). The SATARA
# sibling's header ("inv no | inv date | qty | free | batchno | product name | ... | ledger
# account") produces a completely different compact run, so this can only ever fire here.
_HEADER_RUN = "invnoexpdatedlnopincodeproductnamebatchnoqtyfreewp"


def _firm_name(rows, header_idx):
    """The reporting distributor's name — the first non-empty banner line above the header
    (row 0, e.g. "DEEPALI DRUG DISTRIBUTORS PVT LTD"). Falls back to the "For <firm>" trailer
    if the banner is somehow blank. Returns "" only if neither is present."""
    for row in rows[:header_idx]:
        text = cell_text(row[0]) if row else ""
        if text:
            return text
    for row in rows[header_idx + 1 :]:
        for cell in row:
            text = cell_text(cell)
            low = text.lower()
            if low.startswith("for ") and len(text) > 4:
                return text[4:].strip()
    return ""


def detect(rows):
    head_cells = rows[:12]
    head = compact(" ".join(" ".join(cell_text(c) for c in r) for r in head_cells))
    if _TITLE not in head or _HEADER_RUN not in head:
        return False
    return detect_header_row(rows) is not None


def parse_outward_detail_firm_partywise(rows):
    header_idx = detect_header_row(rows)
    if header_idx is None:
        return [], {}
    headers = [str(h) if h else f"col_{i}" for i, h in enumerate(rows[header_idx])]
    records, detected = records_from_mapped(headers, rows, header_idx)

    firm = _firm_name(rows, header_idx)
    if firm:
        for record in records:
            if not str(record.get("party_name", "")).strip():
                record["party_name"] = firm
    return records, detected
