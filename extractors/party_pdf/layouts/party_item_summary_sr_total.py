import re

from extractors.party_pdf.party_area import extract_party_and_area


# A trailing numeric token: int / decimal, thousands-comma, optional leading sign.
# Anchored so unit words ("ML", "GM"), codes ("AC-50") and hyphenated product
# fragments ("GA-6", "AMOCLAFIX-625TAB") are never mistaken for numbers.
_NUMTOK = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")

# Control / metadata / band-header prefixes (compared upper-cased, whitespace-
# collapsed). Everything here is skipped and can never become a party or a row.
_CTRL_PREFIXES = (
    "PARTY /",
    "REPORT FOR",
    "COMPANY",
    "D E S C",
    "QTY.",
    "TOTAL",
    "GRAND TOTAL",
    "CONTINUED",
    "PAGE NO",
    "GSTIN",
    "PHONE",
    "E-MAIL",
    "***",
)


def _trailing_numbers(tokens):
    """Return the maximal run of trailing numeric tokens (in original order)."""
    run = []
    for tok in reversed(tokens):
        if _NUMTOK.match(tok):
            run.append(tok)
        else:
            break
    run.reverse()
    return run


def parse_party_item_summary_sr_total(text):
    """Marg/Busy 'PARTY / ITEM WISE SALES SUMMARY' — the wide 3-band
    SALE / SALES RETURN / TOTAL layout with an AVR.RATE column (12 trailing
    numbers per product row). Not a busy_tally variant: busy_tally rows carry
    5-6 numbers, these carry 12.

    Structure::

        <PARTY NAME>-<LOCATION>                          (bare band heading)
          <desc> <S_qty> <S_free> <S_amt> <SR_qty> <SR_free> <SR_amt> <SR_%>
                 <T_qty> <T_free> <AVR.RATE> <T_amt> <T_%>
          ...
        ----                                             (dashed rule)
        TOTAL : ...                                      (per-party subtotal)

    The trailing 12 numbers of a data line are, in order::

        [S_qty, S_free, S_amt, SR_qty, SR_free, SR_amt, SR_%,
         T_qty, T_free, AVR_RATE, T_amt, T_%]

    Canonical mapping uses the SALE band: product_name<-desc, qty<-S_qty,
    free_qty<-S_free, amount<-S_amt, rate<-AVR_RATE. Party bands are split with
    extract_party_and_area(raw, 'busy_tally') (NAME-LOCATION on the final '-'),
    matching the GREEN xlsx sibling (party '24 HOURS MEDICAL.DUNGARPUR',
    location 'DUNGARPUR'). The letterhead vendor name reprinted at each page top
    sits immediately after a 'Continued..' line; it is skipped so continuation
    rows stay attributed to the party open before the page break.
    """
    H = ["Party Name", "Area", "Product Name", "Qty", "Free", "Rate", "Amount"]
    rows = []
    cur_name, cur_area = "", ""
    skip_next_band = False

    for raw in text.split("\n"):
        s = re.sub(r"\s+", " ", raw.strip())
        if not s or set(s) <= set("-"):
            continue
        su = s.upper()

        # A 'Continued..' page-break flag: the very next band-like line is the
        # reprinted letterhead vendor name (a page header, not a party).
        if su.startswith("CONTINUED"):
            skip_next_band = True
            continue

        # Control / metadata / band-header / footer lines.
        if su.startswith(_CTRL_PREFIXES) or "PAGE NO" in su or "END OF REPORT" in su:
            continue

        tokens = s.split()
        tail = _trailing_numbers(tokens)
        if len(tail) >= 12:
            cols = tail[-12:]
            desc = " ".join(tokens[: len(tokens) - 12]).strip()
            if not desc or cur_name == "":
                continue
            s_qty, s_free, s_amt = cols[0], cols[1], cols[2]
            avr_rate = cols[9]
            rows.append([
                cur_name,
                cur_area,
                desc,
                s_qty.replace(",", ""),
                s_free.replace(",", ""),
                avr_rate.replace(",", ""),
                s_amt.replace(",", ""),
            ])
            skip_next_band = False
            continue

        # Otherwise a bare band heading with letters -> current party.
        if re.search(r"[A-Za-z]", s):
            if skip_next_band:
                skip_next_band = False  # reprinted letterhead vendor name
                continue
            cur_name, cur_area = extract_party_and_area(s, "busy_tally")

        skip_next_band = False

    return H, rows
