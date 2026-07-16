import inspect
import io
import re
import time

import pdfplumber

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
        except Exception as e:
            result["parse_error"] = str(e)
            result["parsed_headers"] = []
            result["parsed_rows"] = []
    else:
        result["parsed_headers"] = []
        result["parsed_rows"] = []
    result["runtime_ms"] = int((time.perf_counter() - started) * 1000)
    return result
