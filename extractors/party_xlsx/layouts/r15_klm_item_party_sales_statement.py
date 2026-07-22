"""KLM MARG "Sales Statement" — item-wise / party-wise, single-column TEXT-in-xlsx.

AKASH MEDICOSE "KLM PEDIA.xlsx" (Marg ERP export). A fixed-width text report has been
flattened into ONE column (col0), one physical Excel row per printed line::

    KLM LABORATORIES (PEDIA)
    Sales Statement from 01-05-2026 to 31-05-2026
    ==========================================================================
    Item Name                      Party Name                    Transaction Invoice No. Batch         Exp.  Type            Quantity      Free     M.R.P.       Sale   Tax       Sale       Tax
                                                                    Date    No.         No.           Date                                                     Price  %age     Amount    Amount
    CETALORE-M SYP 60ML            PRAKASH GENERAL STORES MANEDRA 16-05-2026 AM2627-01640KL05H24     07-2026 Sales                  1         -      93.28      71.07  5.00      68.94      3.44
    DESOSOFT CREAM 10GM            SHIV.MEDICAL STORE (ANUPPUR)   08-05-2026 AM2627-01346BJ601       12-2027 Sales                  5         1     140.63     107.15  5.00     642.90     32.15
    ...
    <item>                        <party>                        16-05-2026 AMCH-03115  0070824D    07-2026 Sales                  -         2     225.00     160.71  5.00       0.00      0.00   <- free-only (qty '-')
    <item>                        <party>                        17-05-2026 CNB00008    PWWAF-13    04-2026 Wastage               -1         -     150.00     150.00  5.00    -101.25     -5.06   <- Wastage: NEGATIVE qty + NEGATIVE amount
                                                       Total                                                                 210         11                                  23244      2731

LAYOUT (positional, fixed-width for the two text cells; space-run for the numeric tail):
    Item Name   <- col chars [0:31]      -> product_name
    Party Name  <- col chars [31:61]     -> party_name (trade name + glued town, kept whole)
    then a space-run tail on the remainder [61:]:
        Transaction Date  dd-mm-yyyy     -> invoice_date
        Invoice No.                      -> invoice_number
        Batch No.        (optional)      -> batch_no
        Exp. Date        MM-YYYY (opt)   -> (dropped)
        Type             Sales|Wastage
        Quantity   (int, '-'=0, may be negative on Wastage) -> qty
        Free       (int, '-'=0)          -> free_qty
        M.R.P.                           -> mrp
        Sale Price                       -> rate
        Tax %age                         -> (dropped, tax rate not tax value)
        Sale Amount   (may be negative)  -> amount
        Tax Amount    (may be negative)  -> tax_amount

qty and value are SEPARATE columns, mapped by exact header text — qty is NEVER derived
from Sale Amount. Wastage lines carry the vendor's own negative qty and negative sale
amount, so they net correctly into the printed Total.

RECONCILE (this file, 75 rows): sum qty = 210, sum free = 11, sum Sale Amount = 23244.16,
sum Tax Amount = 2730.77 — EXACT to the printed Total (210 / 11 / 23244 / 2731).

Title+header gated on the compact "Sales Statement from" banner AND the exact contiguous
header run "Item Name Party Name Transaction Invoice ..." which no other corpus file
carries, so it can only ever claim this Marg item/party Sales Statement export.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

# Two-part fingerprint. The banner alone ("sales statement from") is shared by area-wise
# variants, so we also require the exact leading header run of THIS column layout.
_TITLE_TOKEN = "salesstatementfrom"
_HEADER_TOKEN = "itemnamepartynametransactioninvoice"

# Fixed-width boundaries of the two leading text cells.
_ITEM_END = 31
_PARTY_END = 61

# Numeric tail, anchored on the Type word. Quantity may be '-' (0) or signed; Free '-'/int;
# Sale Amount / Tax Amount may be negative (Wastage). Tax %age sits between Sale Price and
# Sale Amount and is dropped (it is a rate, not a value).
_TAIL_RE = re.compile(
    r"\s(?P<type>Sales|Wastage|Purchase|Sales Return|Purchase Return"
    r"|Breakage|Expiry|Stock Transfer)\s+"
    r"(?P<qty>-\d+|-|\d+)\s+"
    r"(?P<free>-|\d+)\s+"
    r"(?P<mrp>[\d,.]+)\s+"
    r"(?P<rate>[\d,.]+)\s+"
    r"(?P<taxp>[\d,.]+)\s+"
    r"(?P<amount>-?[\d,.]+)\s+"
    r"(?P<tax>-?[\d,.]+)\s*$"
)

# The remainder [61:] starts: dd-mm-yyyy <invoice> [batch] [MM-YYYY] Type ...
_HEAD_RE = re.compile(r"^\s*(?P<date>\d{2}-\d{2}-\d{4})\s+(?P<inv>\S+)(?P<mid>.*?)\s+(?:Sales|Wastage|Purchase|Breakage|Expiry|Stock Transfer)")
_EXP_RE = re.compile(r"\b\d{2}-\d{4}\b")


def _lines(rows):
    return [cell_text(r[0]) if r and r[0] is not None else "" for r in rows]


def _header_idx(lines):
    for i, line in enumerate(lines[:25]):
        if _HEADER_TOKEN in compact(line):
            return i
    return None


def detect(rows):
    lines = _lines(rows)
    head = compact(" ".join(lines[:20]))
    return _TITLE_TOKEN in head and _header_idx(lines) is not None


def _num(tok):
    if not tok or tok == "-":
        return 0.0
    return float(tok.replace(",", ""))


def parse_klm_item_party_sales_statement(rows):
    detected = {
        "Item Name": "product_name",
        "Party Name": "party_name",
        "Transaction Date": "invoice_date",
        "Invoice No.": "invoice_number",
        "Batch No.": "batch_no",
        "Quantity": "qty",
        "Free": "free_qty",
        "M.R.P.": "mrp",
        "Sale Price": "rate",
        "Sale Amount": "amount",
        "Tax Amount": "tax_amount",
    }
    lines = _lines(rows)
    hidx = _header_idx(lines)
    if hidx is None:
        return [], detected

    records = []
    for line in lines[hidx + 1:]:
        if len(line) < _PARTY_END:
            continue
        remainder = line[_PARTY_END:]
        tail = _TAIL_RE.search(remainder)
        if not tail:
            continue
        product = line[:_ITEM_END].strip()
        party = line[_ITEM_END:_PARTY_END].strip()
        if not product or not party:
            continue

        invoice = ""
        invoice_date = ""
        batch = ""
        hm = _HEAD_RE.match(remainder)
        if hm:
            invoice_date = hm.group("date")
            invoice = hm.group("inv")
            mid = hm.group("mid").strip()
            # mid may be a batch token and/or the MM-YYYY exp date; drop the exp, keep batch.
            mid = _EXP_RE.sub("", mid).strip()
            if mid:
                batch = mid.split()[0]

        qty = tail.group("qty")
        rec = {
            "product_name": product,
            "party_name": party,
            "invoice_date": invoice_date,
            "invoice_number": invoice,
            "batch_no": batch,
            "qty": "0" if qty == "-" else qty,
            "free_qty": "0" if tail.group("free") == "-" else tail.group("free"),
            "mrp": tail.group("mrp").replace(",", ""),
            "rate": tail.group("rate").replace(",", ""),
            "amount": tail.group("amount").replace(",", ""),
            "tax_amount": tail.group("tax").replace(",", ""),
        }
        records.append(rec)

    return records, detected
