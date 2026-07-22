import inspect
import io
import re
import time

import pdfplumber

from core.line_ledger import audit_text_lines

from extractors.party_pdf.constants import FORMAT_LABELS, FORMAT_REPORT_TYPE
from extractors.party_pdf.detect import detect_format
from extractors.party_pdf.registry import PARSERS


# Producers whose PDFs use a CID encoding pdfminer can't map but PyMuPDF can, AND
# for which we have a dedicated parser. The PyMuPDF fallback is adopted only when the
# recovered text matches one of these, so it never relabels an unparseable file.
_CID_FALLBACK_SIGNATURES = ("medivision",)


def _decode_cid(text):
    if "(cid:" not in text:
        return text
    return re.sub(r"\(cid:(\d+)\)", lambda m: chr(int(m.group(1)) + 29), text)


_GLYPH_PAREN = re.compile(r"(\d\.\d{2})\)+[ \t]*$")


def _strip_glyph_paren(text):
    """A (cid:12) control glyph decodes (via _decode_cid's +29 map) to a spurious
    ')' glued onto the final money value at a line end, e.g. "... 141.90 0.03)".
    That trailing ')' breaks the end-anchored row patterns of text parsers and the
    whole row is silently dropped (confirmed in busy_tally, unisolve and
    area_item_summary). Strip such a trailing ')' run, but ONLY on lines where ')'
    is unbalanced (more ')' than '('), so a genuine accounting-negative "(1,234.56)"
    or a product name carrying parens is left untouched."""
    if ")" not in text:
        return text
    out = []
    for ln in text.split("\n"):
        if _GLYPH_PAREN.search(ln) and ln.count(")") > ln.count("("):
            ln = _GLYPH_PAREN.sub(r"\1", ln)
        out.append(ln)
    return "\n".join(out)


# --- TT-glyph-index subset decode (SURANA DRUG DISTRIBUTORS print-captures) ---
# Some PCL/GDI print-to-PDF captures embed subset fonts whose /Encoding
# /Differences names are raw TrueType glyph indices ("/g22") with NO ToUnicode
# CMap. pdfminer then emits '(cid:N)' for codes < 32 (which _decode_cid turns
# into control-char garbage) and identity WinAnsi chars for codes >= 32, so the
# whole document is unreadable although it renders perfectly. The original face
# is the PCL-resident Monotype font whose glyph order is fixed (3=space,
# 4..29=A..Z, 131..156=a..z, 613='0', 616..624='1'..'9', punctuation below), so
# the text is fully recoverable: char code -> /gN name -> glyph index -> char.
# The decode is attempted only when the already-extracted text is drowning in
# control chars (_looks_gid_garbled: >=500 of them AND >=25% of all chars; the
# worst normal corpus file has 11) and is ADOPTED only when the decoded text
# contains one of _TTGID_SIGNATURES, i.e. a header our detect chain already
# routes (pipe_delimited). A gid-subset PDF from another producer whose font
# has a different glyph order would fail the signature test and stay exactly as
# garbled as before -- this fallback can never relabel any other file.
_TTGID_SIGNATURES = ("srno|entry no", "item wise sale,sale return")

_TTGID_PUNCT = {
    314: "&",
    345: ",",
    346: "'",
    347: ":",
    348: ".",
    350: "-",
    373: "/",
    374: "|",
    377: "—",
    383: "(",
    384: ")",
    592: "'",
    681: "%",
}


def _ttgid_char(n):
    """Monotype/PCL TrueType glyph index -> character (None when unknown)."""
    if n == 3:
        return " "
    if 4 <= n <= 29:
        return chr(65 + n - 4)  # A..Z
    if 131 <= n <= 156:
        return chr(97 + n - 131)  # a..z
    if n == 613:
        return "0"
    if 616 <= n <= 624:
        return chr(49 + n - 616)  # 1..9
    return _TTGID_PUNCT.get(n)


def _looks_gid_garbled(text):
    """True when extracted text is mostly control-char garbage (gid subsets)."""
    if not text:
        return False
    ctl = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\r\t")
    return ctl >= 500 and ctl * 4 >= len(text)


_GID_NAME = re.compile(r"g\d+")
_CID_TOKEN = re.compile(r"\(cid:(\d+)\)")


def _decode_gid_differences(pdf_bytes):
    """Decode a gid-subset PDF via the fixed TT glyph-index map.

    Returns (page_texts, full_text) or None when the file does not carry the
    pure /gN /Differences signature (any non-gid glyph name aborts) or when
    more than 1% of mapped glyphs are unknown to _ttgid_char.
    """
    from pdfminer.pdftypes import resolve1
    from pdfplumber.utils import extract_text as _layout_text

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        # 1. per-font code -> glyph-index maps from /Encoding /Differences.
        diffs = {}
        for page in pdf.pages:
            fonts = resolve1(resolve1(page.page_obj.resources).get("Font")) or {}
            for fref in fonts.values():
                fdict = resolve1(fref)
                base = fdict.get("BaseFont")
                fname = getattr(base, "name", None) or str(base)
                if fname in diffs:
                    continue
                enc = resolve1(fdict.get("Encoding"))
                if not isinstance(enc, dict):
                    return None
                arr = resolve1(enc.get("Differences"))
                if not arr:
                    return None
                mp = {}
                code = None
                for item in arr:
                    if isinstance(item, (int, float)):
                        code = int(item)
                        continue
                    gname = getattr(item, "name", None) or str(item)
                    if not _GID_NAME.fullmatch(gname):
                        return None  # not a pure gid subset -> leave untouched
                    mp[code] = int(gname[1:])
                    code += 1
                diffs[fname] = mp
        if not diffs:
            return None
        # 2. decode chars page by page and rebuild the layout text with the
        # same engine page.extract_text() uses, so column alignment matches
        # what normally-encoded siblings of the same report produce.
        page_texts = []
        full = ""
        mapped = unmapped = 0
        for page in pdf.pages:
            dec = []
            for ch in page.chars:
                token = ch["text"]
                cid = _CID_TOKEN.fullmatch(token)
                if cid:
                    code = int(cid.group(1))
                elif len(token) == 1:
                    code = ord(token)  # WinAnsi identity for codes >= 32
                else:
                    code = None
                gmap = diffs.get(ch["fontname"])
                if gmap is not None and code in gmap:
                    mapped += 1
                    rune = _ttgid_char(gmap[code])
                    if rune is None:
                        unmapped += 1
                        rune = "�"
                    ch = dict(ch, text=rune)
                dec.append(ch)
            text = _layout_text(dec) or ""
            page_texts.append(text)
            full += text + "\n"
    if not mapped or unmapped * 100 > mapped:
        return None
    return page_texts, full


def _extract_with_pymupdf(pdf_bytes):
    """Re-extract text via PyMuPDF (MuPDF). Used only as a fallback when pdfminer
    (pdfplumber) fails to map a PDF's glyphs. Returns (pages, full_text)."""
    import fitz  # PyMuPDF

    pages = []
    full_text = ""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text") or ""
            full_text += text + "\n"
            pages.append(
                {
                    "page_number": i + 1,
                    "width": float(page.rect.width),
                    "height": float(page.rect.height),
                    "char_count": len(text),
                    "line_count": 0,
                    "rect_count": 0,
                    "text": text,
                }
            )
    return pages, full_text


def extract_pdf(pdf_bytes):
    started = time.perf_counter()
    result = {"pages": [], "file_size_bytes": len(pdf_bytes), "source": "pdf"}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        result["total_pages"] = len(pdf.pages)
        full_text = ""
        nr = nl = 0
        for page in pdf.pages:
            text = _strip_glyph_paren(_decode_cid(page.extract_text() or ""))
            full_text += text + "\n"
            nr += len(page.rects)
            nl += len(page.lines)
            result["pages"].append(
                {
                    "page_number": page.page_number,
                    "width": float(page.width),
                    "height": float(page.height),
                    "char_count": len(page.chars),
                    "line_count": len(page.lines),
                    "rect_count": len(page.rects),
                    "text": text,
                }
            )
    # pdfminer (pdfplumber) returns almost nothing for PDFs with a non-standard CID
    # encoding (e.g. MediVision Platinum's 'Adobe-UTF-8' collection): the glyphs are
    # embedded but pdfminer can't map them, so full_text collapses to a few stray chars
    # and the file is misread as scanned/empty. PyMuPDF maps the same CIDs correctly.
    # Fall back to it ONLY when pdfplumber produced almost no text, and adopt the result
    # only when it is dramatically larger -- so every file pdfplumber already reads (all
    # 552 baselines yield thousands of chars) is untouched by construction.
    if len(full_text.strip()) < 200:
        try:
            mu_pages, mu_full = _extract_with_pymupdf(pdf_bytes)
            recovered = any(sig in mu_full.lower() for sig in _CID_FALLBACK_SIGNATURES)
            if recovered and len(mu_full.strip()) > max(500, len(full_text.strip()) * 3):
                result["pages"] = mu_pages
                result["total_pages"] = len(mu_pages)
                result["text_source"] = "pymupdf_fallback"
                full_text = mu_full
                nr = nl = 0
        except Exception:
            pass
    # Gid-subset print-captures (see _decode_gid_differences above). Gate is
    # structural (text drowning in control chars) and adoption additionally
    # requires a known-parseable signature in the decoded text, so every file
    # the branch does not fire for is byte-for-byte unaffected.
    if _looks_gid_garbled(full_text):
        try:
            decoded = _decode_gid_differences(pdf_bytes)
            if decoded:
                dec_pages, dec_full = decoded
                low = dec_full.lower()
                if any(sig in low for sig in _TTGID_SIGNATURES):
                    for meta, ptext in zip(result["pages"], dec_pages):
                        meta["text"] = ptext
                        meta["char_count"] = len(ptext)
                    full_text = dec_full
                    result["text_source"] = "ttgid_differences_decode"
        except Exception:
            pass
    fmt = detect_format(full_text, nr, nl)
    result["detected_format"] = fmt
    result["format_label"] = FORMAT_LABELS.get(fmt, "Unknown")
    result["auto_report_type"] = FORMAT_REPORT_TYPE.get(fmt, "Party-wise Sales")
    parser = PARSERS.get(fmt)
    if parser:
        try:
            # Positional parsers (e.g. interleaved-column PDFs) need the raw bytes
            # to read word x-coordinates; text-only parsers are called unchanged.
            if "file_bytes" in inspect.signature(parser).parameters:
                h, r = parser(full_text, file_bytes=pdf_bytes)
            else:
                h, r = parser(full_text)
            # Parse-time fallbacks: a broad-but-strict parser sometimes yields
            # nothing on a sub-variant it can't shape-match (busy_tally chokes on
            # fractional qty / missing-free / 'Pcs' unit tokens; marg_register
            # chokes on the 'Mf-Customerwise' register whose customer is a bare
            # heading). When the primary returns NOTHING, retry with a more
            # tolerant sibling. Guarded on an EMPTY result, so every file the
            # primary already parses is byte-for-byte unaffected.
            # Each entry is an ORDERED list of tolerant siblings tried in turn until
            # one yields rows. marg_register's blank-amount register falls to
            # prathna_register; its SrNo-first AMOUNT-bearing twin (AAGAM / VISNAGAR)
            # is rejected by prathna's $-anchored regex and is caught by the
            # klm_sales_detail_register sibling next. Order matters: prathna is tried
            # FIRST so every file it already parses is byte-for-byte unaffected.
            _FALLBACKS = {
                "busy_tally": ("party_item_summary_nofree",),
                "busy_tally_itemwise": ("party_item_summary_nofree",),
                "marg_register": ("prathna_register", "klm_sales_detail_register"),
                "marg_register_itemwise": ("prathna_register", "klm_sales_detail_register"),
                # KLM BILL WISE "Sales Statement" shares bajaj's exact header but its
                # scheme-qty body makes parse_bajaj return 0 rows; every genuine bajaj
                # file parses (rows>0) so it never reaches this fallback.
                "bajaj_salestatement": ("klm_salestatement_scheme",),
            }
            if not r and fmt in _FALLBACKS:
                for alt_key in _FALLBACKS[fmt]:
                    alt = PARSERS.get(alt_key)
                    if alt is None:
                        continue
                    h2, r2 = alt(full_text)
                    if r2:
                        h, r = h2, r2
                        fmt = alt_key
                        result["detected_format"] = fmt
                        result["format_label"] = FORMAT_LABELS.get(fmt, "Unknown")
                        result["auto_report_type"] = FORMAT_REPORT_TYPE.get(
                            fmt, "Party-wise Sales"
                        )
                        break
            result["parsed_headers"] = h
            result["parsed_rows"] = r
            # Line-accounting ledger (core/line_ledger): classify every input
            # line against the RAW parser output — here, after the fallback
            # chain resolves, values still match the printed text (no pack
            # strip / canonicalization / enrichment yet). Read-only: it never
            # alters rows; triage's UNACCOUNTED_LINES gate consumes it.
            try:
                result["line_audit"] = audit_text_lines(full_text, r, headers=h)
            except Exception:  # ledger must never break extraction
                result["line_audit"] = {"applicable": False, "reason": "ledger error"}
        except Exception as e:
            result["parse_error"] = str(e)
            result["parsed_headers"] = []
            result["parsed_rows"] = []
    else:
        result["parsed_headers"] = []
        result["parsed_rows"] = []
    result["runtime_ms"] = int((time.perf_counter() - started) * 1000)
    return result
