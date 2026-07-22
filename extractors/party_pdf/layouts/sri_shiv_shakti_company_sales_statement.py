import re

# SRI SHIV SHAKTI PHARMA "SALES STATEMENT OF THE COMPANY < KLM >".
#
# Product-grouped party statement. Structure:
#   SRI SHIV SHAKTI PHARMA / address
#   SALES STATEMENT OF THE COMPANY < KLM >
#   REPORT FROM :<d> TO <d>
#   S.NO PARTY NAME BILL NO. DATE QTY RATE DEAL DISC GST AMOUNT
#   Product Name :<PRODUCT> Packing :<PACK>        <- product band
#   <SNO>|<PARTY NAME> <BILL> <DD/MM/YYYY> <QTY> <RATE> [<DEAL>] <DISC> <GST> <AMOUNT>
#   ...
#   Total : <qty> <amount>                          <- per-product footer
#   ...
#   TOTAL <qty> <disc?> <amount>                    <- grand total (3rd number)
#
# The S.NO is pipe-separated from the party name ('1|DR.BR PANDAEY'); the row's
# AMOUNT (GST-inclusive sale value) is the LAST token and reconciles EXACTLY to
# both the per-product 'Total :' lines and the grand 'TOTAL' 3rd number.

_DATA_RE = re.compile(r"^(?P<sno>\d+)\|(?P<party>.+?)\s+(?P<bill>[A-Z]?\d{4,})\s+"
                      r"(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<rest>.+)$")
_PROD_RE = re.compile(r"^Product\s+Name\s*:(?P<prod>.*?)\s+Packing\s*:(?P<pack>.*)$", re.I)


def parse_sri_shiv_shakti_company_sales_statement(text):
    headers = ["Party Name", "Product Name", "Invoice No", "Invoice Date",
               "Qty", "Rate", "Amount"]
    rows = []
    product = ""
    for raw in text.splitlines():
        ln = raw.rstrip()
        if not ln:
            continue
        pm = _PROD_RE.match(ln)
        if pm:
            product = pm.group("prod").strip()
            continue
        dm = _DATA_RE.match(ln)
        if dm:
            toks = dm.group("rest").split()
            if len(toks) < 3:
                continue
            # QTY RATE [DEAL DISC GST] AMOUNT — amount is the last token (GST-incl.)
            amount = toks[-1]
            qty = toks[0]
            rate = toks[1]
            rows.append([dm.group("party").strip(), product, dm.group("bill"),
                         dm.group("date"), qty, rate, amount])
        # all other lines (page headers, 'Total :', 'TOTAL', glyph noise) are skipped
    return headers, rows
