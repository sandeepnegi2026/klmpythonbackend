"""Marg qty-only 'Stock and Sales' group-wise report (BASHA, KAMAKSHI, ...).

Header:  Group/Item Name | Pack | Opening Qty | Recd.Qty | Issued Qty | ClsQty
Reconciles: ClsQty = Opening + Recd - Issued  (pure quantity movement; no value or
free columns per row — the report's value totals live in a header block).

The text layer splits one product across 2-3 near-identical `top` values (e.g. the
name/pack on one line, some of the 4 numbers on the next), and interior columns are
frequently BLANK, so a flat token-count parse drops most rows. We instead read word
x-positions with pdfplumber, cluster words into visual rows, and bucket each number
into its column by x-centre using the printed header as the anchor. Long product
names that wrap to a following name-only line are folded back into the product.
"""
import io
import re

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")
_ANCHOR_TOKENS = ("Recd.Qty", "ClsQty")  # tokens unique to this header


def _is_num(t):
    return bool(_NUM_RE.fullmatch(t.replace(",", ""))) and any(c.isdigit() for c in t)


def _to_f(t):
    try:
        return float(t.replace(",", ""))
    except ValueError:
        return 0.0


def _header_anchors(words):
    """If this word row is the column header, return the 4 column x0 anchors."""
    labels = {w["text"]: w["x0"] for w in words}
    if not all(tok in labels for tok in _ANCHOR_TOKENS):
        return None
    if "Opening" not in labels or "Issued" not in labels:
        return None
    return {
        "opening": labels["Opening"],
        "recd": labels["Recd.Qty"],
        "issued": labels["Issued"],
        "closing": labels["ClsQty"],
    }


def _cluster_rows(words, tol=6):
    """Group words into visual rows: tops within `tol` px of the cluster's first
    top belong together (handles the 1-2 px sub-line jitter that splits a product)."""
    by_top = {}
    for w in words:
        by_top.setdefault(round(w["top"]), []).append(w)
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


_DIVISION_BAND = re.compile(r"^KLM\b", re.I)


def _approx(a, b, tol=0.5):
    return abs(a - b) <= tol


def _matches_totals(op, rc, iss, cl, sums):
    """True when the four numbers equal a band's running column sums -> a genuine
    (sub)total row, not a product whose cells jittered onto this baseline."""
    return (_approx(op, sums["op"]) and _approx(rc, sums["rc"])
            and _approx(iss, sums["is"]) and _approx(cl, sums["cl"]))


def _emit(records, band_sums, grand_sums, name, pack, op, rc, iss, cl):
    records.append({
        "product_name": name,
        "pack": pack,
        "opening_stock": op,
        "purchase_stock": rc,
        "sales_qty": iss,
        "closing_stock": cl,
    })
    for acc in (band_sums, grand_sums):
        acc["op"] += op
        acc["rc"] += rc
        acc["is"] += iss
        acc["cl"] += cl


def parse_marg_stock_recd_issued(text, file_bytes=None):
    if not file_bytes:
        return []
    import pdfplumber

    records = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        anchors = None
        # A product whose name+pack rendered with NO inline numbers because its
        # numeric cells jittered onto the next text baseline (which then collides
        # with the following subtotal label). Held here so those numbers can be
        # re-attached instead of lost with the total row.
        pending = None
        # Running column sums so a genuine (sub)total row can be told apart from a
        # product's own cells that jittered onto the total baseline: a real total
        # equals these sums; a blank product must NOT inherit the total's numbers.
        band_sums = {"op": 0.0, "rc": 0.0, "is": 0.0, "cl": 0.0}
        grand_sums = {"op": 0.0, "rc": 0.0, "is": 0.0, "cl": 0.0}
        for page in pdf.pages:
            words = page.extract_words()
            for row_words in _cluster_rows(words):
                row_words = sorted(row_words, key=lambda w: w["x0"])
                found = _header_anchors(row_words)
                if found:
                    anchors = found
                    continue
                if not anchors:
                    continue

                op_x, rc_x, is_x, cl_x = (anchors["opening"], anchors["recd"],
                                          anchors["issued"], anchors["closing"])
                b1 = (op_x + rc_x) / 2.0
                b2 = (rc_x + is_x) / 2.0
                b3 = (is_x + cl_x) / 2.0
                num_min = op_x - 15  # numbers live at/after the Opening column

                col = {}
                name_toks, pack_toks = [], []
                for w in row_words:
                    cx = (w["x0"] + w["x1"]) / 2.0
                    if _is_num(w["text"]) and cx >= num_min:
                        if cx < b1:
                            col["op"] = _to_f(w["text"])
                        elif cx < b2:
                            col["rc"] = _to_f(w["text"])
                        elif cx < b3:
                            col["is"] = _to_f(w["text"])
                        else:
                            col["cl"] = _to_f(w["text"])
                    elif w["x0"] < 185:
                        name_toks.append(w["text"])
                    elif w["x0"] < num_min:
                        pack_toks.append(w["text"])

                name = " ".join(name_toks).strip()
                low = name.lower()
                has_nums = bool(col)

                op = col.get("op", 0.0)
                rc = col.get("rc", 0.0)
                iss = col.get("is", 0.0)
                cl = col.get("cl", 0.0)

                # A group band header ("KLM COSMO", name-only, no pack) opens a new
                # band -> reset the band running sums so its subtotal is comparable.
                is_band_header = bool(
                    _DIVISION_BAND.match(name) and " " in name
                    and not pack_toks and "total" not in low)

                # band / total / footer lines -> skip and break any name-wrap carry.
                # When a total label carries numbers and a pending product (name+pack,
                # no inline numbers) is waiting, those numbers belong to that product
                # ONLY if they are its own cells jittered one baseline down -- never
                # when they are the band/grand column totals (a genuinely empty
                # product must stay empty and be dropped).
                if "total" in low or low.startswith("page") or is_band_header:
                    if (pending is not None and has_nums
                            and not (op == 0 and rc == 0 and iss == 0 and cl == 0)
                            and not _matches_totals(op, rc, iss, cl, band_sums)
                            and not _matches_totals(op, rc, iss, cl, grand_sums)):
                        _emit(records, band_sums, grand_sums,
                              pending[0], pending[1], op, rc, iss, cl)
                    pending = None
                    if is_band_header:
                        band_sums = {"op": 0.0, "rc": 0.0, "is": 0.0, "cl": 0.0}
                    continue

                if not has_nums:
                    # a name-only continuation of the previous product (wrapped name)
                    if name and not pack_toks and records:
                        records[-1]["product_name"] = (
                            records[-1]["product_name"] + " " + name).strip()
                    elif name:
                        # name(+pack) row with no numbers: hold it in case its numeric
                        # cells jittered onto the next (total) baseline.
                        pending = (name, " ".join(pack_toks).strip())
                    continue

                pending = None
                if not name:
                    continue

                if op == 0 and rc == 0 and iss == 0 and cl == 0:
                    continue  # phantom / all-blank row

                pack = " ".join(pack_toks).strip()
                _emit(records, band_sums, grand_sums, name, pack, op, rc, iss, cl)
    return records
