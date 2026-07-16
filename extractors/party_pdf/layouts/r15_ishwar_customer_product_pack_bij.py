import re

from extractors.party_pdf.party_area import extract_party_and_area

# ---------------------------------------------------------------------------
# "Customer-Wise Product-Wise Sales" — customer-banded, product-wise sale
# register with a PACK column and a NON-standard invoice-type token ("BIJ").
# Source file: SHRI ISHWAR MEDICAL AGENCY/Party report/PEDIA__72163658.PDF
# (SHREE ISHWAR MEDICAL AGENCYS, Dhule; Unisolve/Softworld-style print).
#
# Exact column header (gate token, whitespace-stripped + lowercased):
#     Product Name Pack Inv/DM No Date Batch No. Qty Free Rate Value
#     -> productnamepackinv/dmnodatebatchno.qtyfreeratevalue
#
# This shares the report TITLE ("Customer-Wise Product-Wise Sales") with the
# generic `unisolve` billwise layout, but its rows carry a distinct shape:
#   * a leading PACK column ("BIJ") that is a plain alpha token, NOT one of
#     unisolve's INV/DM/INC invoice-type keywords, so parse_unisolve 0-rows it.
#   * columns:  <code> <product name> <PACK> <Inv/DM No> <date> <batch>
#               <qty> [<free>] <rate> <value>
#
# Example rows (note optional Free between Qty and Rate):
#   11390060 SOFIBAR SYNDET BAR 75GM BIJ 5377 16/05/26 SKS0126 3 132.20 396.60
#   11390072 SOFIKID ZN DROPS 15ML BIJ 6605 27/05/26 AZS01AAB 5 1 71.07 355.35
#
# Body nesting (one block per customer):
#   Customer: [A269] ANAND MEDICAL& GENRAL STORES, PLOT NO 54/26   <- band
#   ============================================================
#   11390060 SOFIBAR SYNDET BAR 75GM BIJ 5377 16/05/26 SKS0126 3 132.20 396.60
#   ...
#   Total: 4954.05                                                  <- subtotal (skip)
#
# Field map (SACRED — qty and value never mixed):
#   Customer: [..] <NAME>, <ADDR>  -> party_name / area (via extract_party_and_area)
#   <code>                         -> Product Code
#   <product name incl pack strength> -> Product Name
#   PACK (BIJ)                     -> Pack column (kept as printed, not numeric)
#   Inv/DM No                      -> Inv No
#   Date / Batch                   -> Date / Batch
#   Qty                            -> Qty      (sales_qty, the PAID quantity)
#   Free                           -> Free     (sales_free; 0 when column absent)
#   Rate                           -> Rate     (unit price; NEVER a quantity)
#   Value                          -> Value    (sole money column)
# Party sale report -> only the sales side exists; RATE*QTY(+free) ~= VALUE and
# per-customer 'Total:' + report 'Total Value :' corroborate the numbers.
# ---------------------------------------------------------------------------

_NUM = r"\d[\d,]*(?:\.\d+)?"

# <code> <name> <PACK-alpha> <inv-no-digits> <dd/mm/yy> <batch> <qty> [free] <rate> <value>
_ROW = re.compile(
    rf"^(?P<code>\d{{7,}})\s+"
    rf"(?P<name>.+?)\s+"
    rf"(?P<pack>[A-Za-z][A-Za-z0-9/.\-]*)\s+"
    rf"(?P<inv>\d+)\s+"
    rf"(?P<date>\d{{2}}/\d{{2}}/\d{{2}})\s+"
    rf"(?P<batch>\S+)\s+"
    rf"(?P<qty>{_NUM})\s+"
    rf"(?:(?P<free>{_NUM})\s+)?"
    rf"(?P<rate>{_NUM})\s+"
    rf"(?P<value>{_NUM})\s*$"
)

_CUST = re.compile(r"^Customer:\s*\[\w+\]\s*(.+)$")


def _f(tok):
    return tok.replace(",", "")


def parse_r15_ishwar_customer_product_pack_bij(text):
    H = [
        "Party Name",
        "Area",
        "Product Code",
        "Product Name",
        "Pack",
        "Inv No",
        "Date",
        "Batch",
        "Qty",
        "Free",
        "Rate",
        "Value",
    ]
    rows, cur_raw = [], ""
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue

        cm = _CUST.match(s)
        if cm:
            cur_raw = cm.group(1).strip()
            continue

        m = _ROW.match(s)
        if not m:
            continue

        name, area = extract_party_and_area(cur_raw, "unisolve")
        rows.append(
            [
                name,
                area,
                m.group("code"),
                m.group("name").strip(),
                m.group("pack"),
                m.group("inv"),
                m.group("date"),
                m.group("batch"),
                _f(m.group("qty")),
                _f(m.group("free")) if m.group("free") else "0",
                _f(m.group("rate")),
                _f(m.group("value")),
            ]
        )
    return H, rows
