"""KLM/Marg "Customer VS Item Summaries" party-item summary (KAMAKSHI MEDICAL
DISTRIBUTORS and siblings).

Masthead:  KAMAKSHI MEDICAL DISTRIBUTORS
Title:     Customer VS Item Summaries DD/Mon/YYYY To DD/Mon/YYYY
Header:    Group/ Name  S.Qty  S.Free  SR.Fre  NetQty+F  Replace  Sale Value
           Sale Ret  Total   (wraps to a 2nd physical line: "e ree ment Value Value")

Structure is party-banded (Marg zero-suppressed convention):
    <BARE CUSTOMER NAME heading>
        <product name>  <variable trailing numbers>
        ...
    Totals  <numbers>
    ... repeat ...
    Grand Total <numbers>

Zero-valued columns are SUPPRESSED, so a product row carries a VARIABLE trailing
number count:
  * 4 numbers = S.Qty, NetQty+Free, Sale Value, Total
        -> Qty = n1, Free = 0,        Amount = n3
  * 5 numbers = S.Qty, S.Free, NetQty+Free, Sale Value, Total
        -> Qty = n1, Free = n2,       Amount = n4   (== NetQty - S.Qty)
Qty/Free columns are integer-valued "NN.00" (comma-thousands); the two money
columns are equal (Sale Value == Total, no sale-returns in these files).

Product names WRAP to the next physical line (a name-only fragment with NO trailing
numbers, e.g. "EFFERVE TAB", "SOAP", "MOISTURIZ LOTION", "NEW", "POUCHES"): fold it
back into the product row that was just emitted for the current party. A no-number
line that does NOT follow a just-emitted product row is a bare customer heading and
becomes the current party.

The text layer for these files is clean (columns are reliably space-separated and
the trailing numbers split correctly), so we parse the flat text by trailing-number
count -- the same skeleton as the sibling party_item_summary_nofree layout.
"""
import re

# money / value token: "N,NNN.NN" (exactly 2 decimals), optional sign
_MONEY = re.compile(r"-?[\d,]+\.\d{2}")
# any numeric-value token (qty "NN.00" or money) used for the trailing run
_VALNUM = re.compile(r"-?[\d,]+\.\d{2}")

_SKIP_SUBSTR = (
    "customer vs item summaries",   # title
    "group/",                       # column header line ("Group/ Name S.Qty ...")
    "kamakshi medical",             # masthead
)


def _to_num(tok):
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return 0.0


def _trailing_nums(toks):
    """Return the maximal run of value-number tokens at the END of the token list."""
    run = []
    for t in reversed(toks):
        if _VALNUM.fullmatch(t.replace(",", "")):
            run.append(t)
        else:
            break
    run.reverse()
    return run


def parse_klm_customer_vs_item_summary(text, file_bytes=None):
    H = ["Party Name", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    party = ""
    last_was_product = False  # did we just emit a product row for the current party?

    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s:
            continue
        low = s.lower()

        # masthead / title / column-header / wrapped-header-continuation / paging
        if any(k in low for k in _SKIP_SUBSTR):
            last_was_product = False
            continue
        if low.startswith("page ") or low.startswith(("e ree", "e ", "ment ")):
            # "e ree ment Value Value" wrapped column-header continuation
            if low.startswith("e ree") or (low.startswith("e ") and "value" in low):
                last_was_product = False
                continue
        # address / phone masthead line (digits + comma-heavy, no product pattern)
        if re.match(r"^\d{2}-\d", s):
            last_was_product = False
            continue

        toks = s.split()
        trail = _trailing_nums(toks)
        n = len(trail)
        name = " ".join(toks[: len(toks) - n]).strip() if n else s

        # subtotal / grand-total lines -> boundary, do not emit
        if low.startswith("totals") or low.startswith("grand total"):
            last_was_product = False
            continue

        # a genuine product row: >=4 trailing numbers with a name in front
        if n >= 4 and name:
            qty = _to_num(trail[0])
            if n >= 5:
                free = _to_num(trail[1])
                net = _to_num(trail[2])
                amount = _to_num(trail[-2])   # Sale Value (== Total)
                # prefer derived free when the net column corroborates it
                if abs((qty + free) - net) > 0.01 and net > 0:
                    free = net - qty
            else:  # n == 4 -> S.Qty, NetQty+Free, Sale Value, Total (free suppressed)
                free = 0.0
                amount = _to_num(trail[-2])
            rows.append([
                party,
                name,
                f"{qty:g}",
                f"{free:g}",
                f"{amount:g}",
            ])
            last_was_product = True
            continue

        # a line with 1-3 trailing numbers but no name is noise; skip
        if n and not name:
            last_was_product = False
            continue

        # no trailing numbers -> either a wrapped product-name fragment or a party heading
        if n == 0 and re.search(r"[A-Za-z]", s):
            if last_was_product and rows:
                # wrapped continuation of the immediately-preceding product name
                rows[-1][1] = (rows[-1][1] + " " + s).strip()
            else:
                party = s
                last_was_product = False
            continue

        last_was_product = False

    return H, rows
