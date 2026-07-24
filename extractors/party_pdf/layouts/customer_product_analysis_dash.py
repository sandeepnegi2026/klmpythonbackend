import re

# CD PHARMA "Customer & Product Analysis" export (C.D. Pharma, KLM PEDIA/... party
# report). Shares the ProfitMaker/Daxinsoft title 'Customer & Product Analysis' and
# the exact column header 'Inv.No Date Product Pack Batch Qty Free Rate Value', but
# its detail rows and the report-period line carry HYPHEN dates (DD-MM-YYYY), whereas
# every existing ProfitMaker export in the corpus uses SLASH dates (DD/MM/YYYY).
# ProfitMaker's parser rejects hyphen dates outright (_DATE is slash-only), so those
# files 0-row under it -- hence this sibling, gated on the hyphen-date period line.
#
# Layout:
#   Title line:   'Customer & Product Analysis'
#   Period line:  'From 01-05-2026 To 27-05-2026 Page : 1'   <- hyphen dates
#   Column head:  'Inv.No Date Product Pack Batch Qty Free Rate Value'
#   Party band:   'Customer :<NAME>'          (no City:/Area:/Add: suffix)
#   Item rows:    '<INV> DD-MM-YYYY <product ... pack ... batch> Qty Free Rate Value'
#
# The Product/Pack/Batch middle segment is captured whole as the product name and
# Pack/Batch are left blank so the pipeline's extract_pack_from_product peels the
# pack; splitting the batch here corrupts rows and is intentionally NOT attempted
# (identical policy to the customer_product_sales sibling). Qty/Free/Rate/Value are
# kept as four independent columns; qty is NEVER derived from the value column.

_CUST_RE = re.compile(r"^Customer\s*:\s*(.+?)\s*$")

_NUM = r"-?\d[\d,]*\.\d{2}"
# Invoice code: 1-4 leading letters + digits (BD00184, SR00597, ...). Anchored so a
# 'Total:' / separator line can never be mistaken for a detail row.
_ROW_RE = re.compile(
    r"^([A-Z]{1,4}\d+)\s+(\d{2}-\d{2}-\d{4})\s+(.+?)\s+"
    r"(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")\s*$"
)


def parse_customer_product_analysis_dash(text):
    H = [
        "Party Name",
        "Inv No",
        "Date",
        "Product Name",
        "Pack",
        "Batch",
        "Qty",
        "Free",
        "Rate",
        "Value",
    ]
    rows = []
    cur_party = ""
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        cm = _CUST_RE.match(s)
        if cm:
            cur_party = cm.group(1).strip()
            continue
        if s.startswith(("Total", "Grand Total", "From ", "Page", "Inv.No")):
            continue
        rm = _ROW_RE.match(s)
        if rm:
            rows.append(
                [
                    cur_party,
                    rm.group(1),
                    rm.group(2),
                    rm.group(3).strip(),
                    "",
                    "",
                    rm.group(4),
                    rm.group(5),
                    rm.group(6),
                    rm.group(7),
                ]
            )
    return H, rows
