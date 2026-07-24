"""
"AreaCity Wise Sale Report" — a Marg (SHREE UNITED / KLM) *pivot* XLS export. There is no
customer column: the report is one row per product, and the product's total quantity is
broken out across a wide band of per-area-city QUANTITY-ONLY columns headed generically
``AC1 .. ACn``::

    PrCode | Product | Pack | Qty | SPTRVal | AC1 | AC2 | ... | ACn

``Qty`` is the product's TOTAL quantity (== sum of that row's ``AC*`` cells) and ``SPTRVal``
is the product's TOTAL rupee value (there is NO per-cell value in the grid). The real area
names live in a LEGEND printed below the data, one entry per AC column::

    AC1(308.98-0.09)AGRIPADA MUMBAI   AC2(2576.17-0.75)ANDHERI(E) MUMBAI   #

i.e. ``AC<n>(<area value>-<area %>)<CITY NAME>``.  The bare ``AC<n>`` grid headers therefore
carry the party (area-city) grain — mirroring how the other area-wise summaries in this route
treat the route/area as the customer.

The parser UNPIVOTS every non-blank ``AC<n>`` cell into one (product, city) record, resolving
``AC<n>`` to its legend city as ``party_name``/``party_location`` and carrying the cell as
``qty``.  Because no per-cell value exists, each product's ``SPTRVal`` is apportioned across
its own area cells in proportion to their quantity (largest-remainder rounding), so the
emitted ``taxable_value``/``amount`` sum back EXACTLY to ``SPTRVal`` per product and to the
report's printed grand total.  The printed ``TOTAL`` row and the legend/footer lines are
skipped.

Gated on the distinctive compact title token ``areacitywisesalereport`` PLUS the exact
``PrCode Product Pack Qty SPTRVal AC1`` header signature, so it can only ever claim this
specific export (proven corpus-unique; zero theft of the paired-column
``product_areawise_pivot`` sibling, which has ``<AREA> qty``/``<AREA> amt`` pairs and no
``AC<n>`` grid).
"""
import re

from core.header_match import normalize

from extractors.party_xlsx.parse_common import cell_text, compact

_LEGEND_RE = re.compile(r"AC(\d+)\(([\d.]+)-[\d.]+\)\s*([^#]*?)\s*(?=AC\d+\(|#|$)")


def _find_header_idx(rows):
    """Row index of the ``PrCode | Product | Pack | Qty | SPTRVal | AC1 ..`` header."""
    for idx, row in enumerate(rows[:20]):
        cells = [normalize(c) for c in row]
        if "prcode" not in cells or "product" not in cells:
            continue
        has_ac = any(re.fullmatch(r"ac\d+", c) for c in cells)
        if has_ac:
            return idx
    return None


def _ac_columns(headers):
    """Return {ac_number(int): column_index} for every ``AC<n>`` grid header."""
    out = {}
    for idx, raw in enumerate(headers):
        m = re.fullmatch(r"ac(\d+)", normalize(raw))
        if m:
            out[int(m.group(1))] = idx
    return out


def _legend_map(rows, start_idx):
    """Parse the ``AC<n>(<value>-<pct>)<CITY>`` legend below the data into {n: city}."""
    cities = {}
    for row in rows[start_idx:]:
        if not row:
            continue
        text = " ".join(cell_text(c) for c in row).strip()
        if "AC" not in text or "(" not in text:
            continue
        for m in _LEGEND_RE.finditer(text):
            n = int(m.group(1))
            city = m.group(3).strip()
            if city and n not in cities:
                cities[n] = city
    return cities


def _apportion(total_value, qtys):
    """Split ``total_value`` across ``qtys`` proportional to qty, largest-remainder rounded
    to 2 dp so the parts sum EXACTLY to ``total_value``. ``qtys`` are non-negative floats."""
    tot_qty = sum(qtys)
    n = len(qtys)
    if n == 0:
        return []
    if tot_qty <= 0:
        # No qty to weight by: put the whole value on the first cell.
        parts = [0.0] * n
        parts[0] = round(total_value, 2)
        return parts
    cents_total = int(round(total_value * 100))
    raw = [total_value * 100 * q / tot_qty for q in qtys]
    floors = [int(x) for x in raw]
    remainder = cents_total - sum(floors)
    order = sorted(range(n), key=lambda i: raw[i] - floors[i], reverse=True)
    for k in range(max(0, remainder)):
        floors[order[k % n]] += 1
    return [c / 100.0 for c in floors]


def detect(rows):
    if _find_header_idx(rows) is None:
        return False
    title = compact(" ".join(" ".join(cell_text(c) for c in r) for r in rows[:6]))
    return "areacitywisesalereport" in title


def parse_areacity_wise_sale_pivot(rows):
    header_idx = _find_header_idx(rows)
    if header_idx is None:
        return [], {}
    headers = [cell_text(c) for c in rows[header_idx]]

    col_prcode = col_product = col_pack = col_qty = col_val = None
    for idx, raw in enumerate(headers):
        low = normalize(raw)
        if col_prcode is None and low == "prcode":
            col_prcode = idx
        elif col_product is None and low == "product":
            col_product = idx
        elif col_pack is None and low in ("pack", "packing", "unit"):
            col_pack = idx
        elif col_qty is None and low == "qty":
            col_qty = idx
        elif col_val is None and low in ("sptrval", "value", "amount", "salevalue"):
            col_val = idx
    if col_product is None:
        return [], {}

    ac_cols = _ac_columns(headers)
    if not ac_cols:
        return [], {}

    # Find where the product grid ends (TOTAL row) so the legend below is not misread as data.
    data_end = len(rows)
    for i in range(header_idx + 1, len(rows)):
        first = cell_text(rows[i][0]) if rows[i] else ""
        if normalize(first).startswith("total"):
            data_end = i
            break

    cities = _legend_map(rows, data_end)

    def _num(s):
        try:
            return float(str(s).replace(",", ""))
        except (ValueError, TypeError):
            return 0.0

    records = []
    for raw in rows[header_idx + 1: data_end]:
        if not raw:
            continue
        product = cell_text(raw[col_product]) if col_product < len(raw) else ""
        if not product or normalize(product).startswith("total"):
            continue
        pack = cell_text(raw[col_pack]) if (col_pack is not None and col_pack < len(raw)) else ""
        row_val = _num(raw[col_val]) if (col_val is not None and col_val < len(raw)) else 0.0

        # Collect this product's non-blank area cells.
        cells = []  # (ac_number, qty_float)
        for n, cidx in ac_cols.items():
            if cidx >= len(raw):
                continue
            q = cell_text(raw[cidx]).strip()
            if not q:
                continue
            qf = _num(q)
            if qf == 0:
                continue
            cells.append((n, qf))
        if not cells:
            continue

        parts = _apportion(row_val, [q for _, q in cells])
        for (n, qf), part in zip(cells, parts):
            city = cities.get(n, f"AC{n}")
            records.append({
                "product_name": product,
                "pack": pack,
                "party_name": city,
                "party_location": city,
                "qty": f"{qf:g}",
                "taxable_value": f"{part:.2f}",
                "amount": f"{part:.2f}",
            })

    detected = {headers[col_product]: "product_name"}
    if col_pack is not None:
        detected[headers[col_pack]] = "pack"
    if col_qty is not None:
        detected[headers[col_qty]] = "qty"
    if col_val is not None:
        detected[headers[col_val]] = "taxable_value"
    return records, detected
