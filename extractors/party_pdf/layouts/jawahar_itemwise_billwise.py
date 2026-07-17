"""JAWAHAR AGENCIES 'Itemwise-Billwise' sales register (KLM/Marg family).

Title line:  `Itemwise-Billwise : KLMPH,KLMPD,KLMGY,KLCOR,KLM,KCOR,COSMQ,KLMCO ...`
Column header (echoed once per printed page):
    `Bill No. Date Name of Customer Place Batch Qty Free Value`

Structure is ITEM-BANDED with a PARTY-PER-ROW body (the inverse of the
party-banded billwise layouts already in the engine):

  <PRODUCT NAME + pack>                         <- band header line
    BillNo Date Name-of-Customer Place Batch Qty Free Value   <- detail rows
    ...
  Total for <product> Qty Free Value            <- band subtotal (skipped)
  ...
  Grand Total 493736.07                         <- report footer (used for recon)

BillNo looks like JDB00751 / JAA00103 / JON00454 / JDC00194 (J + 2 letters + 5
digits). party_name (Name of Customer) is taken from EACH detail row.

Why positional (pdfplumber word x-positions), not flat text: the PDF text layer
character-INTERLEAVES the tail of the customer name with the Place token on some
rows (e.g. `... GENERAL STONRAENSDED` = "STORE"+"NANDED", `... STORDEHSARMABAD`),
because Name and Place are adjacent fixed-width columns. Reading word x0 lets us
keep the clean Name column (x0 < ~262) apart from Place (x0 ~264+), Batch, and the
right-aligned Qty / Free / Value numeric columns, which stay clean. Bare `-` in a
numeric column means nil -> 0.
"""
import io
import re
from collections import defaultdict

# Bill No. forms across the Itemwise-Billwise family:
#   JAWAHAR AGENCIES -> J + 2 uppercase letters + 5 digits (JDB00751, JAA00103)
#   RAAJYOG MEDICO   -> 3 letters + 5 digits (RMC00847) AND a single-letter
#                       R + 7 digits (R2601646). The R\d{7} form is the DERMACOR
#                       variant's primary invoice series; without it 18/27 of its
#                       detail rows were silently dropped (they slid into the
#                       product-band branch and overwrote product_name). Neither
#                       R\d{7} nor the 3L5D form ever appears on a JAWAHAR product
#                       band (those start with a product word), so widening the
#                       gate cannot steal a JAWAHAR line -- its 391 rows stay
#                       byte-for-byte identical.
_BILL_RE = re.compile(r"^(?:[A-Z]{3}\d{5}|R\d{7})$")
_DATE_RE = re.compile(r"^\d{2}/\d{2}$")
_NUM_RE = re.compile(r"^-?\d[\d,]*\.\d+$")

# Column x boundaries (page width 595, header anchors: Place@266 Batch@338
# Qty@465 Free@501 Value@568). Detail-row numbers sit right-aligned in three
# clean bands; name/place/batch sit left of them.
_NAME_MAX = 262   # Name-of-Customer text lives left of this
_PLACE_MAX = 330  # Place tokens: [_NAME_MAX, _PLACE_MAX)
_BATCH_MAX = 430  # Batch tokens: [_PLACE_MAX, _BATCH_MAX)
_QTY_LO, _QTY_HI = 440, 495     # Qty column band (centre ~470)
_FREE_LO, _FREE_HI = 495, 540   # Free column band (centre ~514)
_VALUE_LO = 540                 # Value column band (right of this)

_PACK_TAIL_RE = re.compile(r"\b(\d+\s*\*\s*\d+|\d+(?:\.\d+)?\s*(?:ML|GM|MG|GML|MCG|KG|LT|GR)\b|\d+'?S)\b", re.I)


def _to_f(tok):
    tok = tok.strip()
    if tok in ("-", "", "."):
        return 0.0
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return 0.0


def _cluster_rows(words, tol=4):
    """Group words into visual rows by their `top`, tolerating sub-line jitter."""
    by_top = defaultdict(list)
    for w in words:
        by_top[round(w["top"])].append(w)
    rows, cur, start = [], [], None
    for top in sorted(by_top):
        if start is None or top - start <= tol:
            if start is None:
                start = top
            cur.extend(by_top[top])
        else:
            rows.append(cur)
            cur, start = list(by_top[top]), top
    if cur:
        rows.append(cur)
    return rows


def _strip_pack(name):
    """Strip the trailing (often duplicated) pack from a product band header.

    e.g. `BLEMGUARD FACE SERUM 30ML 30ML` -> ("BLEMGUARD FACE SERUM", "30ML"),
         `AMOCLAFIX 625 TABS 1*10`        -> ("AMOCLAFIX 625 TABS", "1*10").
    """
    toks = name.split()
    pack = ""
    # collapse a duplicated trailing pack token (`30ML 30ML`)
    if len(toks) >= 2 and toks[-1].upper() == toks[-2].upper():
        pack = toks[-1]
        toks = toks[:-1]
    m = _PACK_TAIL_RE.search(name)
    if m and not pack:
        pack = m.group(0)
    # trailing 1*10 style pack
    if len(toks) >= 1 and re.match(r"^\d+\s*\*\s*\d+$", toks[-1]):
        pack = toks[-1]
        base = " ".join(toks[:-1]).strip()
        return base, pack
    if pack and toks and toks[-1] == pack:
        base = " ".join(toks[:-1]).strip()
        return base, pack
    return " ".join(toks).strip(), pack


def parse_jawahar_itemwise_billwise(text, file_bytes=None):
    headers = ["Party Name", "Place", "Product Name", "Pack",
               "Inv No", "Date", "Batch", "Qty", "Free", "Amount"]
    if not file_bytes:
        return headers, []

    import pdfplumber

    rows = []
    product_name = None
    product_pack = ""

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            for rw in _cluster_rows(words):
                rw = sorted(rw, key=lambda w: w["x0"])
                if not rw:
                    continue
                first = rw[0]["text"]
                line = " ".join(w["text"] for w in rw)
                low = line.lower()

                # --- page furniture / band totals -> skip (don't touch product) ---
                if (
                    low.startswith("bill no")
                    or low.startswith("total for")
                    or low.startswith("grand total")
                    or low.startswith("itemwise-billwise")
                    or low.startswith("jawahar")
                    or low.startswith("ganjewar")
                    or low.startswith("page ")
                    or re.match(r"^\d{2}/\d{2}/\d{4}\b", line)
                ):
                    continue

                # --- detail row: leading BillNo then dd/mm date ---
                if _BILL_RE.match(first) and len(rw) >= 2 and _DATE_RE.match(rw[1]["text"]):
                    inv = first
                    date = rw[1]["text"]
                    name_toks, place_toks, batch_toks = [], [], []
                    qty = free = value = None
                    for w in rw[2:]:
                        cx = (w["x0"] + w["x1"]) / 2.0
                        txt = w["text"]
                        # numeric columns (right-aligned) by x-centre band
                        if cx >= _VALUE_LO:
                            value = _to_f(txt)
                        elif _FREE_LO <= cx < _FREE_HI:
                            free = _to_f(txt)
                        elif _QTY_LO <= cx < _QTY_HI:
                            qty = _to_f(txt)
                        elif w["x0"] < _NAME_MAX:
                            name_toks.append(txt)
                        elif w["x0"] < _PLACE_MAX:
                            place_toks.append(txt)
                        elif w["x0"] < _BATCH_MAX:
                            batch_toks.append(txt)
                    party = " ".join(name_toks).strip()
                    place = " ".join(place_toks).strip()
                    batch = " ".join(batch_toks).strip()
                    if not party or product_name is None:
                        continue
                    rows.append([
                        party, place, product_name, product_pack,
                        inv, date, batch,
                        qty if qty is not None else 0.0,
                        free if free is not None else 0.0,
                        value if value is not None else 0.0,
                    ])
                    continue

                # --- otherwise: a PRODUCT band header (has no leading BillNo) ---
                # product bands start at the left margin (x0 ~26) and carry no
                # trailing numeric value column.
                if rw[0]["x0"] < 60 and not _NUM_RE.match(first):
                    base, pack = _strip_pack(line)
                    if base:
                        product_name = base
                        product_pack = pack
    return headers, rows
