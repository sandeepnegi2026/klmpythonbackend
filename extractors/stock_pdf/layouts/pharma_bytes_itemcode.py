import io
import re

from extractors.stock_pdf.parse_common import (
    _nums,
    _skip_line,
    _split_product_pack,
    _to_number,
)

# ---------------------------------------------------------------------------
# Multi-division combined SST variant (SOURABH MEDICOSE "KLM SST"): the SAME
# "Item Name | Code | Packing | Op Stk | Rcvd. Qty. | Issue Qty | Cl Stk |
# Exp Qty | Dump Qty | Order" header, but the report concatenates EVERY KLM
# division band (8 bands, each closed by its own "Op. Value :" footer) instead
# of exporting one division per file. Zero cells print BLANK, so the collapsed
# plaintext loses column alignment and the positional number mapping below
# mis-binds roughly half the rows (Issue read as Rcvd, Cl read as Issue, packs
# like "60 ML"/"10" swallowed as Op Stk). The numbers are RIGHT-ALIGNED to the
# header tokens' right edges, so for this variant we re-read the page words
# with pdfplumber and bucket each number into the column whose right edge it
# aligns with (klm_stock_sales_month precedent). Keyed on the multi-division
# shape (>= 2 "Op. Value" division footers) so the single-division sibling
# exports (7x MP + Sales Diff + SST baselines) keep the legacy text path
# byte-identical; additionally reconcile-guarded (>= 90% of rows must satisfy
# Op + Rcvd - Issue == Cl) so any coordinate drift falls back to the legacy
# result instead of emitting garbage.
# ---------------------------------------------------------------------------

# printed left-to-right column order; each maps to the RIGHT edge (x1) of the
# second token of the header pair ("Op Stk" -> x1 of "Stk"), except Order.
_XCOL_LABELS = ("Op", "Rcvd", "Issue", "Cl", "Exp", "Dump", "Order")
_XNUM_RE = re.compile(r"-?\d[\d,]*\.?\d*$")
_XSKIP_RE = re.compile(
    r"^(MFG\d|Op\. Value|Clo\. Value|Sales Value|Cum\. Sales|Report Date|Page|"
    r"SOURABH|Stock and Sales|Item Name)",
    re.I,
)


def _xheader_edges(line_words):
    """If this word row is the column header, return (edges, code_x0, pack_x0)."""
    texts = [w["text"] for w in line_words]
    if "Packing" not in texts or "Rcvd." not in texts:
        return None
    edges = {}
    labels = iter(_XCOL_LABELS)
    want = next(labels)
    for idx, w in enumerate(line_words):
        if w["text"].rstrip(".") == want:
            if want == "Order":
                edges[want] = w["x1"]
            elif idx + 1 < len(line_words):
                edges[want] = line_words[idx + 1]["x1"]
            try:
                want = next(labels)
            except StopIteration:
                break
    if len(edges) < 5 or "Op" not in edges or "Cl" not in edges:
        return None
    code_x0 = next((w["x0"] for w in line_words if w["text"] == "Code"), None)
    pack_x0 = next((w["x0"] for w in line_words if w["text"] == "Packing"), None)
    if code_x0 is None or pack_x0 is None:
        return None
    return edges, code_x0, pack_x0


def _parse_pharma_bytes_xcoord(file_bytes):
    """Column-aligned re-read of the multi-division variant via word x1 edges."""
    import pdfplumber

    records = []
    division = ""
    edges = None
    code_x0 = pack_x0 = 0.0
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines = []
            for w in sorted(page.extract_words(), key=lambda w: (w["top"], w["x0"])):
                if lines and abs(w["top"] - lines[-1][0]) < 2.0:
                    lines[-1][1].append(w)
                else:
                    lines.append((w["top"], [w]))
            for _, lw in lines:
                lw.sort(key=lambda w: w["x0"])
                s = " ".join(w["text"] for w in lw).strip().replace("`", "")
                hdr = _xheader_edges(lw)
                if hdr:
                    edges, code_x0, pack_x0 = hdr
                    continue
                if edges is None or _skip_line(s) or _XSKIP_RE.match(s):
                    continue
                name_toks, pack_toks, code = [], [], ""
                name_words = []
                vals = {}
                bad = False
                for w in lw:
                    t = w["text"].replace("`", "")
                    if w["x0"] < code_x0 - 20:
                        name_toks.append(t)
                        name_words.append(w)
                    elif w["x0"] < pack_x0 - 12:
                        code = t
                    elif w["x1"] < edges["Op"] - 40:
                        pack_toks.append(t)
                    else:
                        tt = t.replace(",", "")
                        if not _XNUM_RE.fullmatch(tt):
                            bad = True
                            break
                        col = min(edges, key=lambda k: abs(edges[k] - w["x1"]))
                        if abs(edges[col] - w["x1"]) > 15:
                            bad = True
                            break
                        vals[col] = float(tt)
                if bad:
                    continue
                # glued code: 'COSMOQ BRIGHTENING SERUM 30ML 30ML007524' -- the
                # pack text fuses with the 6-digit code into one word that
                # starts just LEFT of the code column but overflows into it.
                # Peel the trailing 6 digits off as the code (legacy re.sub
                # precedent in the text path below).
                if not code and name_toks:
                    lastw = name_words[-1]
                    gm = re.search(r"(\d{6})$", name_toks[-1])
                    if gm and lastw["x1"] > code_x0:
                        code = gm.group(1)
                        prefix = name_toks[-1][: gm.start()]
                        name_toks = name_toks[:-1] + ([prefix] if prefix else [])
                # division band: KLM-prefixed line WITHOUT grid numbers (item
                # rows may legitimately start with 'KLM ' in this export, e.g.
                # 'KLM D3 NANO 30ML' -- those DO carry grid numbers).
                if not vals:
                    if re.match(r"^KLM\s", s, re.I):
                        division = s
                    continue
                if not code:
                    continue
                records.append(
                    {
                        "product_name": " ".join(name_toks),
                        "pack": " ".join(pack_toks),
                        "product_code": code,
                        "division": division,
                        "opening_stock": vals.get("Op", 0.0),
                        "purchase_stock": vals.get("Rcvd", 0.0),
                        "sales_qty": vals.get("Issue", 0.0),
                        "closing_stock": vals.get("Cl", 0.0),
                    }
                )
    return records


def _xreconcile_rate(rows):
    if not rows:
        return 0.0
    ok = sum(
        1
        for r in rows
        if abs(
            r["opening_stock"]
            + r["purchase_stock"]
            - r["sales_qty"]
            - r["closing_stock"]
        )
        < 0.01
    )
    return ok / len(rows)


def parse_pharma_bytes_itemcode(text, file_bytes=None):
    """Pharma Bytes Item-Code: Item Name + 6-digit Code + Packing + Op/Rcvd/Issue/Close/Exp numbers."""
    # Multi-division combined export (>= 2 per-division 'Op. Value' footers):
    # blank zero-cells break the positional mapping below, so re-read by word
    # x-coordinates. Single-division exports (exactly one footer) never enter
    # this branch and keep the legacy output unchanged.
    if file_bytes is not None and len(
        re.findall(r"(?m)^\s*Op\. Value", text)
    ) >= 2:
        try:
            xrecords = _parse_pharma_bytes_xcoord(file_bytes)
        except Exception:
            xrecords = []
        if xrecords and _xreconcile_rate(xrecords) >= 0.90:
            return xrecords
    records = []
    division = ""
    for line in text.splitlines():
        s = line.strip().replace("`", "")
        if _skip_line(s):
            continue
        if re.match(r"^KLM\s", s, re.I):
            division = s
            continue
        if re.match(
            r"^(MFG\d|Op\. Value|Clo\. Value|Sales Value|Report Date|Page|SOURABH)",
            s,
            re.I,
        ):
            continue
        s = re.sub(r"(\D)(\d{6})(?=\s|\D|$)", r"\1 \2 ", s)
        m = re.search(r"\b(\d{6})\b", s)
        if not m:
            continue
        left = s[: m.start()].strip()
        right = s[m.end() :].strip()
        nums = _nums(right.split())
        tokens = left.split()
        if tokens and nums and _to_number(tokens[-1]) == nums[0]:
            pack = tokens[-1]
            name = " ".join(tokens[:-1])
            nums = nums[1:]
        else:
            name, pack = _split_product_pack(left)
        if len(nums) >= 5 and pack and abs(nums[0] - (_to_number(pack) or -1)) < 0.01:
            nums = nums[1:]
        if len(nums) < 2:
            continue
        record = {
            "product_name": name,
            "pack": pack,
            "product_code": m.group(1),
            "division": division,
            "opening_stock": nums[0],
            "purchase_stock": nums[1] if len(nums) > 1 else 0.0,
            "sales_qty": nums[2] if len(nums) > 2 else 0.0,
            "closing_stock": nums[3] if len(nums) > 3 else nums[-1],
        }
        records.append(record)
    return records
