"""
"Customer Vs Groups Report" — KLM / KRISHNA MEDICAL SYNDICATE, single-column TEXT variant.

A KLM ERP ("Customer Vs Groups Report from dd/Mon/yy to dd/Mon/yy") that a text->xlsx
converter has flattened into ONE fixed-width text column (col0) and then SHREDDED: long
report lines are broken across several physical Excel rows and, worse, some customer /
value fragments are interleaved out of order (the diagnosis: only 27 of 43 sale lines
survive as clean one-line rows; the other 16 are torn into interleaved fragments that
cannot be reassembled reliably).

    ฀฀฀฀G AMOCLAFIX-625mg TAB 10s  ฀H            <- ITEM band  (G <item> H)   [product header]
       MOHAN MED & GEN STORES  AMALAPURAM 22/Jun/26 KMS 10280  AN503 318.75  1.0 ... 242.86  242.86  239.22
       ... (per-customer sale lines, blank Free/Replace collapsed) ...
         AMOCLAFIX-6                             <- item rollup label (often truncated)
    3.0  1.0            146.29        438.87        425.70   <- item ROLLUP  (qty free rate gross net)

Every item is bracketed by a ``G <item> H`` header band and a trailing ROLLUP number line
(``qty  free|---  rate  gross  net``). The item ROLLUP reconciles EXACTLY to the source
grand total (band count == rollup count 1:1 on all 7 division files), so it is the ground
truth for value reconciliation.

STRATEGY (hybrid — party detail where recoverable, rollup residual for the shredded rest):
  * Per ITEM window (G-band .. next G-band): emit every CLEAN one-line customer sale row
    ("<name> <town> dd/Mon/yy KMS <bill> <batch> <mrp> <qty> <rate> <gross> <net>", the
    blank Free/Replace collapsed -> a 5-number tail) as a real party row.
  * Then emit ONE rollup-remainder row carrying the residual qty/free/gross/net
    (rollup MINUS the sum of the clean rows already emitted for that item) so the division
    value total still reconciles despite the unrepairable shredded fragments. Its
    party_name is left blank (unknown customer) — flagged via party_location "" .

COLUMN MAP (trailing numeric tail of a clean line, blank Free/Replace collapsed):
    MRP  Qty  Rate  Gross Value  Net Value   ->  qty / rate / amount(=gross) / net_amount
    (Free/Replace are only ever populated on the rollup here, folded into free_qty there.)
product_name/pack <- G-band item (name+pack glued, split downstream by extract_pack).
party_name/party_location <- customer + town (town = trailing UPPER token run of the name
cell). invoice_number <- "KMS <bill>"; invoice_date <- dd/Mon/yy; batch_no <- batch code.

RECONCILE (per division): sum(rollup) == printed source total; e.g. COSMO CORE
qty 144 / free 36 / net 19,840.27 (18 items); the clean detail rows alone recover ~78% of
net, the rollup-remainder rows carry the balance.
"""
import re

from extractors.party_xlsx.parse_common import cell_text, compact

_TITLE_COMPACT = "customervsgroupsreport"
_HEADER_COMPACT = "itemnamecustomername"  # "Item Name / Customer Name Town Date Number Batch MRP..."

# The single fixed-width column is padded with the U+0E00 (฀) filler the converter injects;
# also seen: the box-drawing rule chars. Normalise the filler to a space before parsing.
_NOISE = "฀"

# ITEM band: "G <item name+pack> H" (leading/trailing filler already stripped to spaces).
_BAND_RE = re.compile(r"^G\s+(.*?)\s*H$")

# ROLLUP number line: qty  (free | ---)  rate  gross  net  -- five trailing money tokens.
_ROLLUP_RE = re.compile(
    r"^(\d[\d,]*\.\d)\s+(---|\d[\d,]*\.\d)\s+([\d,]+\.\d\d)\s+([\d,]+\.\d\d)\s+([\d,]+\.\d\d)$"
)

# A KLM/Marg date like 10/Jun/26.
_DATE_RE = re.compile(r"\b(\d{2}/[A-Za-z]{3}/\d{2})\b")

# A clean, complete one-line sale row:
#   <name+town>  dd/Mon/yy  KMS <bill>  <batch>  <mrp> <qty> <rate> <gross> <net>
# Free/Replace are blank (collapsed), so the tail is exactly 5 numeric tokens. The customer
# block before the date is a FIXED-WIDTH pair (a 23-char NAME field then the TOWN), split
# positionally below — the trade name often fills the whole field leaving only a single
# space before the town, so a space-run split would fail.
_DETAIL_RE = re.compile(
    r"^(?P<who>.*?)\s+(?P<date>\d{2}/[A-Za-z]{3}/\d{2})\s+KMS\s+(?P<bill>\d+)\s+(?P<batch>\S+)\s+"
    r"(?P<mrp>[\d,]+\.\d+)\s+(?P<qty>\d[\d,]*\.\d+)\s+(?P<rate>[\d,]+\.\d+)\s+"
    r"(?P<gross>[\d,]+\.\d+)\s+(?P<net>[\d,]+\.\d+)$"
)
# Width of the fixed NAME field (chars) — town begins immediately after it.
_NAME_WIDTH = 23


def _num(tok):
    return float(tok.replace(",", "")) if tok and tok != "---" else 0.0


def _clean_line(cell):
    return cell_text(cell).replace(_NOISE, " ").rstrip()


def _lines(rows):
    return [_clean_line(r[0]) if r and r[0] is not None else "" for r in rows]


def _header_idx(lines):
    for i, line in enumerate(lines[:30]):
        if _HEADER_COMPACT in compact(line):
            return i
    return None


def _split_town(who):
    """Split the fixed-width customer block "<NAME 23-wide><TOWN>" positionally."""
    block = who.lstrip()
    name = block[:_NAME_WIDTH].strip()
    town = block[_NAME_WIDTH:].strip()
    if not name:                       # unexpectedly short -> keep whole cell as the name
        return block.strip(), ""
    return name, town


def detect(rows):
    lines = _lines(rows)
    head = compact(" ".join(lines[:15]))
    return _TITLE_COMPACT in head and _header_idx(lines) is not None


def parse_klm_customer_vs_groups_text(rows):
    detected = {
        "Item Name": "product_name",
        "Customer Name": "party_name",
        "Town": "party_location",
        "Date": "invoice_date",
        "Number": "invoice_number",
        "Batch": "batch_no",
        "Qty": "qty",
        "Free": "free_qty",
        "Rate": "rate",
        "Gross Value": "amount",
        "Net Value": "net_amount",
    }
    lines = _lines(rows)
    hidx = _header_idx(lines)
    if hidx is None:
        return [], detected

    # Index of every ITEM band -> item windows [band .. next band).
    band_at = {}
    for i, line in enumerate(lines[hidx + 1:], start=hidx + 1):
        m = _BAND_RE.match(line.strip())
        if m:
            band_at[i] = m.group(1).strip()
    if not band_at:
        return [], detected
    band_idx = sorted(band_at)

    records = []
    for k, bi in enumerate(band_idx):
        end = band_idx[k + 1] if k + 1 < len(band_idx) else len(lines)
        product = band_at[bi]

        item_rows = []          # clean detail rows emitted for this item
        rollup = None           # last rollup number line in the window
        for i in range(bi + 1, end):
            s = lines[i].strip()
            if not s:
                continue
            rm = _ROLLUP_RE.match(s)
            if rm:
                rollup = rm      # keep the LAST 5-num line = the item rollup
                continue
            if "KMS" not in s or not _DATE_RE.search(s):
                continue
            dm = _DETAIL_RE.match(s)
            if not dm:
                continue         # wrapped / free-only fragment -> covered by rollup residual
            name, town = _split_town(dm.group("who"))
            rec = {
                "party_name": name,
                "product_name": product,
                "invoice_number": "KMS " + dm.group("bill"),
                "invoice_date": dm.group("date"),
                "batch_no": dm.group("batch"),
                "qty": dm.group("qty").replace(",", ""),
                "rate": dm.group("rate").replace(",", ""),
                "amount": dm.group("gross").replace(",", ""),
                "net_amount": dm.group("net").replace(",", ""),
            }
            if town:
                rec["party_location"] = town
            item_rows.append(rec)
            records.append(rec)

        if rollup is None:
            continue
        r_qty = _num(rollup.group(1))
        r_free = _num(rollup.group(2))
        r_gross = _num(rollup.group(4))
        r_net = _num(rollup.group(5))
        rate = rollup.group(3).replace(",", "")

        got_qty = sum(float(r["qty"]) for r in item_rows)
        got_gross = sum(float(r["amount"]) for r in item_rows)
        got_net = sum(float(r["net_amount"]) for r in item_rows)

        res_qty = round(r_qty - got_qty, 2)
        res_gross = round(r_gross - got_gross, 2)
        res_net = round(r_net - got_net, 2)

        # Emit ONE rollup-remainder row when the clean rows did not account for the whole
        # item (the shredded fragments) OR the item carries free issues (free lives only on
        # the rollup here). Party is unknown for the aggregated remainder.
        if res_qty > 0.001 or r_free > 0.001 or res_gross > 0.01 or res_net > 0.01:
            rem = {
                "party_name": "",
                "product_name": product,
                "rate": rate,
                "qty": f"{max(res_qty, 0.0):g}",
                "free_qty": f"{r_free:g}",
                "amount": f"{max(res_gross, 0.0):.2f}",
                "net_amount": f"{max(res_net, 0.0):.2f}",
            }
            records.append(rem)

    return records, detected
