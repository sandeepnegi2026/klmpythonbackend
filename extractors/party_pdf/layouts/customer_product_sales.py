import re

# C.D. ASSOCIATES "Customer & Product Sales" export (KLM divisions COSMO/DERMA/...).
# Title line: 'Customer & Product Sales'
# Column header: 'Inv.No Date Product Pack Batch Qty Free Rate Value'
# Party banding: 'Customer :<name> City:<city>' (city may be empty).
# Item rows: 'MP<n> DD/MM/YYYY <product ... pack ... batch> Qty Free Rate Value'.
#
# The Product/Pack/Batch middle segment is captured whole as the product name and
# Pack/Batch are left blank so the pipeline's extract_pack_from_product peels the
# pack; splitting the batch here corrupts rows and is intentionally NOT attempted.

_CUST_RE = re.compile(r"^Customer\s*:(.*?)\s*City:(.*)$")

_NUM = r"-?\d[\d,]*\.\d{2}"
_ROW_RE = re.compile(
    r"^(MP\d+)\s+(\d{2}/\d{2}/\d{4})\s+(.+?)\s+"
    r"(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")\s*$"
)


def parse_customer_product_sales(text):
    H = [
        "Party Name",
        "City",
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
    cur_party, cur_city = "", ""
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        cm = _CUST_RE.match(s)
        if cm:
            cur_party = cm.group(1).strip()
            cur_city = cm.group(2).strip()
            continue
        rm = _ROW_RE.match(s)
        if rm:
            rows.append(
                [
                    cur_party,
                    cur_city,
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
