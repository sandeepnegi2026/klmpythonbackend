import re


def parse_klm_salestatement_scheme(text):
    """KLM "SALES STATEMENT" bill-wise party report (RELIANCE MEDICO / KLM
    divisions). Same header banner as bajaj_salestatement --
    'BILL NO. PARTY NAME AMOUNT DISCOUNT NET AMT TAX PAYABLE DR/CR NET AMOUNT' --
    but distinguished by the trailing 'TAX PAYABLE DR/CR NET AMOUNT' run (compact
    token 'taxpayabledr/crnetamount') that bajaj_salestatement lacks.

    Structure per bill:
      * a bare date line ('01-06-2026') precedes a day's bills;
      * a bill header line
          '<bill-no> <party name> <amount> <disc> <net> <tax> <dr/cr> <running-bal>'
        where bill-no is a letter-prefixed code ('G001634', 'AD001019');
      * one or more product detail lines
          '<product> <pack> <code> <scheme> <amount> <disc> <net> <tax> <rate>'
        where <scheme> is the ordered/free quantity, printed either as a bare
        integer ('3') or as 'base+free' ('10+5', '40+20', '20+6').

    The party name comes from the bill header; each detail line emits one row
    carrying that party. Qty is read from the scheme column ONLY (base = the
    number before '+', free = the number after '+'); it is never derived from a
    money column. Amount = the detail line's first money column; Rate = the last.
    Headers are kept identical to bajaj_salestatement so downstream field
    mapping is unchanged.
    """
    H = ["Party Name", "Product Name", "Batch", "Qty", "Free", "Rate", "Amount"]
    rows, party = [], ""

    NUM = r"-?[\d,]+\.\d{2}"
    # Bill header: <bill-no letter+digits> <party> + exactly 6 money columns.
    # (amount, disc, net, tax, dr/cr, running-balance)
    BILL = re.compile(
        r"^([A-Z]{1,3}\d{3,})\s+(.+?)\s+" + NUM + r"\s+" + NUM + r"\s+" + NUM
        + r"\s+" + NUM + r"\s+" + NUM + r"\s+" + NUM + r"$"
    )
    # Detail: product/pack + code + scheme + amount + disc + net + tax + rate.
    # scheme base = '<int>', a decimal fraction ('2.50', '9.20'), or a bare '-'
    # (dash = 0 base, e.g. '-+1' free-only lines); optional '+<free>' where free
    # is likewise an int or decimal fraction ('0.50', '1.80').
    SCH = r"(?:\d+(?:\.\d+)?|-)"      # base
    FREE = r"\d+(?:\.\d+)?"           # free
    DETAIL = re.compile(
        r"^(?P<prod>.+?)\s+(?P<code>\S+)\s+(?P<qty>" + SCH + r")(?:\+(?P<free>"
        + FREE + r"))?\s+"
        r"(?P<amt>" + NUM + r")\s+" + NUM + r"\s+" + NUM + r"\s+" + NUM
        + r"\s+(?P<rate>" + NUM + r")$"
    )

    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s or set(s) <= set("-"):
            continue
        su = s.upper()
        if su.startswith((
            "BILL NO", "COMPANY", "GSTIN", "PHONE", "SALES STATEMENT",
            "GRAND", "TOTAL", "SUB TOTAL", "PAGE", "PAGE NO", "CONTINUED",
            "PARTY :", "PARTY:", "RELIANCE", "TIN", "----",
        )) or "E-MAIL" in su or "END OF REPORT" in su:
            continue

        mb = BILL.match(s)
        if mb:
            party = mb.group(2).strip()
            continue

        md = DETAIL.match(s)
        if md and party:
            qty = md.group("qty")
            if qty == "-":            # bare dash base = 0 (free-only line)
                qty = "0"
            rows.append([
                party,
                md.group("prod").strip(),
                md.group("code"),
                qty,
                md.group("free") or "",
                md.group("rate").replace(",", ""),
                md.group("amt").replace(",", ""),
            ])

    return H, rows
