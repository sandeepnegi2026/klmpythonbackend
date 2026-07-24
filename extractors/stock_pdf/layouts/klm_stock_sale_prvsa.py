import io
import re

import pdfplumber

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_numbers,
    _split_product_pack,
)

# Header tokens of the Marg (KLM) "Stock and Sale Report" export, in printed order:
#   Product Name | Pack | OpStk | Purch | PrvSa | Sales | Adj | Cl.St | P.price | Sales Valu | Age
# The last two columns (P.price, Sales Valu) are rupee VALUES; every preceding
# number is an integer quantity.  Interior cells (PrvSa/Sales/Adj/Cl.St) blank
# out for no-movement products, so the flattened text index shifts row to row —
# only x-position column binding is reliable.  We fold:
#   opening_stock <- OpStk, purchase_stock <- Purch, sales_qty <- Sales,
#   closing_stock <- Cl.St, closing_stock_value <- P.price (purchase-price stock
#   value), sales_value <- Sales Valu.  PrvSa (previous-month sale) has no
#   canonical home and is ignored; Adj (signed stock adjustment) is folded into
#   the vendor's printed closing identity (totals band includes it), so we map it
#   to canonical 'shortage' -- triage's effective-sanity adds it back signed
#   (adjusted = base + shortage), matching the file's own reconciliation.

# canonical column keys -> the header word(s) that terminate that column.
# "Sales" appears TWICE in the header (the qty column and the value column
# "Sales Valu"), so we cannot key on the bare word — we bind columns by the
# ordered right-edge (x1) positions of the header tokens instead.
_QTY_HEADERS_ORDER = ["OpStk", "Purch", "PrvSa", "Sales", "Adj", "Cl.St"]
_VAL_HEADERS_ORDER = ["P.price", "SalesValu"]

_COL_MAP = {
    "OpStk": "opening_stock",
    "Purch": "purchase_stock",
    "Sales": "sales_qty",
    "Adj": "shortage",
    "Cl.St": "closing_stock",
    "P.price": "closing_stock_value",
    "SalesValu": "sales_value",
    # "PrvSa" intentionally dropped (previous-month sale, no canonical field).
}


def _cluster_lines(words, tol=3.0):
    lines = {}
    for w in words:
        matched = None
        for y in lines:
            if abs(y - w["top"]) < tol:
                matched = y
                break
        if matched is None:
            matched = w["top"]
        lines.setdefault(matched, []).append(w)
    out = []
    for y in sorted(lines):
        out.append(sorted(lines[y], key=lambda w: w["x0"]))
    return out


def _build_columns(header_line):
    """Return list of (canonical_key, center_x) for the numeric/value columns.

    header_line is a list of word dicts (sorted by x0) for the row that holds
    OpStk ... Sales Valu ... Age.  We walk it left-to-right, greedily assigning
    the expected header tokens in order so the two "Sales" occurrences (qty vs
    value) are disambiguated positionally.
    """
    cols = []
    # Expected ordered header sequence with the canonical key each maps to.
    # "PrvSa" is a placeholder we still need to consume so the column centers stay
    # aligned, but it does not emit an output field.  "Adj" is a signed stock
    # adjustment that participates in the vendor's closing identity, so it now
    # maps to canonical 'shortage' (folded back signed by triage).
    expected = [
        ("OpStk", "opening_stock"),
        ("Purch", "purchase_stock"),
        ("PrvSa", None),
        ("Sales", "sales_qty"),
        ("Adj", "shortage"),
        ("Cl.St", "closing_stock"),
        ("P.price", "closing_stock_value"),
        ("SalesValu", "sales_value"),
    ]
    # Compact-match each expected token against the header words in order.
    words = header_line
    i = 0
    ei = 0
    n = len(words)
    while ei < len(expected) and i < n:
        tok, key = expected[ei]
        w = words[i]
        wtxt = w["text"].replace(" ", "")
        if tok == "SalesValu":
            # spans two words: "Sales" then "Valu"
            if wtxt.lower() == "sales" and i + 1 < n and words[i + 1]["text"].lower().startswith("valu"):
                center = (w["x0"] + words[i + 1]["x1"]) / 2.0
                x1 = words[i + 1]["x1"]
                cols.append((key, center, x1))
                i += 2
                ei += 1
                continue
            i += 1
            continue
        if wtxt.lower() == tok.lower():
            center = (w["x0"] + w["x1"]) / 2.0
            cols.append((key, center, w["x1"]))
            i += 1
            ei += 1
        else:
            i += 1
    return cols


def _is_number(s):
    t = s.replace(",", "")
    if t in ("", "-"):
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False


def _parse_with_coords(file_bytes):
    records = []
    division = ""
    seen_pages = set()
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        cols = None
        for page in pdf.pages:
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue

            # These reports are duplicated across physical pages (Page 1/2 and
            # 2/2 carry byte-identical product tables).  Skip a page whose text
            # signature we have already consumed so products are not counted
            # twice (which would double every quantity downstream).
            page_sig = (page.extract_text() or "").replace("Page 1 /", "").replace(
                "Page 2 /", ""
            )
            page_sig = re.sub(r"Page Number:\S+", "", page_sig)
            page_sig = re.sub(r"\s+", " ", page_sig).strip()
            if page_sig and page_sig in seen_pages:
                continue
            if page_sig:
                seen_pages.add(page_sig)

            lines = _cluster_lines(words)

            # Locate the header row on this page (or reuse a prior page's).
            page_cols = None
            for lw in lines:
                joined = " ".join(w["text"] for w in lw)
                low = joined.lower()
                if "opstk" in low.replace(" ", "") and "cl.st" in low.replace(" ", ""):
                    built = _build_columns(lw)
                    # need at least OpStk, Sales, Cl.St and the two value columns
                    keys = {k for k, _c, _x in built}
                    if {"opening_stock", "sales_qty", "closing_stock"} <= keys:
                        page_cols = built
                        break
            if page_cols:
                cols = page_cols
            if not cols:
                continue

            # min x among qty/value column centers => start of the numeric block.
            first_center = min(c for _k, c, _x in cols)

            for lw in lines:
                joined = " ".join(w["text"] for w in lw).strip()
                if not joined:
                    continue
                low = joined.lower()
                # division line: "of May2026 for KLM,LABS-COSMO DIV"
                m = re.search(r"for\s+(KLM[^\n]*)", joined)
                if m and ("opstk" not in low.replace(" ", "")):
                    division = m.group(1).strip()
                    continue
                if joined.startswith("----") or joined.startswith("===="):
                    continue
                if "opstk" in low.replace(" ", "") and "cl.st" in low.replace(" ", ""):
                    continue
                if any(t in low for t in (
                    "stock and sale report", "rop ratio", "op stk value",
                    "sale prv value", "grand total", "sales value inclueds",
                    "stock valu is calculated", "page number", "document footer",
                )):
                    continue

                # Split words into name-part (left of numeric block) and value words.
                name_words = []
                val_words = []
                for w in lw:
                    if _is_number(w["text"]) and (w["x0"] + w["x1"]) / 2.0 > first_center - 18:
                        val_words.append(w)
                    else:
                        name_words.append(w)

                if not val_words:
                    continue

                # A footer total row has NO product text before the numbers.
                name = " ".join(w["text"] for w in name_words).strip()
                if not name:
                    continue

                # Bin each value word to the nearest column center.  PrvSa
                # (key=None) MUST stay in the candidate set: a PrvSa value that is
                # nearest to its own column must NOT fall through to the
                # neighbouring sales_qty / Adj (shortage) column (which would wreck
                # the reconciliation).  We simply emit nothing for None columns;
                # Adj now carries key='shortage' and is emitted signed.
                row_vals = {}
                for w in val_words:
                    center = (w["x0"] + w["x1"]) / 2.0
                    best_key = None
                    best_dist = 1e9
                    for key, ccenter, _x1 in cols:
                        d = abs(center - ccenter)
                        if d < best_dist:
                            best_dist = d
                            best_key = key
                    if best_key is not None and best_dist < 30:
                        try:
                            row_vals[best_key] = float(w["text"].replace(",", ""))
                        except ValueError:
                            pass

                if not row_vals:
                    continue

                name, pack = _split_product_pack(name)
                name = re.sub(r"\s+", " ", name).strip()
                if not name or len(name) < 3:
                    continue
                # NB: do NOT run the product name through parse_common._skip_line
                # here — it drops any line starting with "KLM " (meant for the
                # division header) and would wrongly discard genuine KLM-branded
                # products such as "KLM -D3 60K CAP".  Header/footer/division rows
                # are already excluded above by their unique tokens, so a remaining
                # name+numbers line is a real product.
                if not re.search(r"[A-Za-z]", name):
                    continue

                r = {"product_name": name, "pack": pack, "division": division}
                for k, v in row_vals.items():
                    r[k] = v
                records.append(r)
    return records


def _parse_text_fallback(text):
    """Best-effort text parser (index-based) for when file_bytes is absent.

    Cannot resolve collapsed blank interior cells reliably, so it only handles
    the common full-row case.  The coordinate path above is the real parser.
    """
    records = []
    division = ""
    for line in text.splitlines():
        s = line.strip()
        m = re.search(r"for\s+(KLM[^\n]*)", s)
        if m and "opstk" not in s.lower().replace(" ", ""):
            division = m.group(1).strip()
            continue
        if _skip_line(s):
            continue
        low = s.lower().replace(" ", "")
        if "opstk" in low or "clstvaluage" in low:
            continue
        prod, tail, _ = _split_product_numbers(s)
        if not prod or len(tail) < 4:
            continue
        vals = _nums(tail)
        if len(vals) < 4:
            continue
        name, pack = _split_product_pack(prod)
        name = re.sub(r"\s+", " ", name).strip()
        if not name or len(name) < 3:
            continue
        # Trailing two decimals are P.price and Sales Valu; the quantities are
        # the integer numbers before them.  With collapsed blanks the qty index
        # is ambiguous, so map only the reliable anchors: last two decimals as
        # values, and use the closing qty as the last integer before them.
        decimals = [v for v in vals if v != int(v)]
        r = {"product_name": name, "pack": pack, "division": division}
        # Heuristic: assume full 6-qty layout collapsed is uncommon in text mode.
        ints = []
        for t in tail:
            tc = t.replace(",", "")
            if re.fullmatch(r"-?\d+", tc):
                ints.append(int(tc))
        if len(ints) >= 1:
            r["closing_stock"] = ints[-1]
        if ints:
            r["opening_stock"] = ints[0]
        if len(decimals) >= 1:
            r["closing_stock_value"] = decimals[0]
        if len(decimals) >= 2:
            r["sales_value"] = decimals[1]
        records.append(r)
    return records


def parse_klm_stock_sale_prvsa(text, file_bytes=None):
    """Marg (KLM) 'Stock and Sale Report' with the OpStk/Purch/PrvSa/Sales/Adj/
    Cl.St/P.price/Sales Valu columns (SRI SENTHIL MEDICAL AGENCIES).

    Interior quantity cells blank out for no-movement products, collapsing the
    flat text index, so parse by header x-position when file_bytes is present.
    """
    if file_bytes is not None:
        try:
            records = _parse_with_coords(file_bytes)
            if records:
                return records
        except Exception:
            pass
    return _parse_text_fallback(text)
