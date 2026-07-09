import io
import re

import pdfplumber

from extractors.stock_pdf.parse_common import _parse_page_range


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
    whole row is silently dropped. Strip such a trailing ')' run, but ONLY on lines
    where ')' is unbalanced (more ')' than '('), so a genuine accounting-negative
    "(1,234.56)" or a product name carrying parens is left untouched."""
    if ")" not in text:
        return text
    out = []
    for ln in text.split("\n"):
        if _GLYPH_PAREN.search(ln) and ln.count(")") > ln.count("("):
            ln = _GLYPH_PAREN.sub(r"\1", ln)
        out.append(ln)
    return "\n".join(out)


def _extract_with_pymupdf(file_bytes, settings):
    """Re-extract text via PyMuPDF (MuPDF), used only as a fallback when pdfminer
    (pdfplumber) fails to map a PDF's glyphs. Returns (all_text, pages, raw_parts)."""
    import fitz  # PyMuPDF

    pages = []
    raw_parts = []
    all_text = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for pi in _parse_page_range(settings.get("page_range"), doc.page_count):
            text = doc[pi].get_text("text") or ""
            raw_parts.append(text)
            all_text += text + "\n"
            pages.append(
                {"page_no": pi + 1, "char_count": len(text),
                 "line_count": 0, "rect_count": 0}
            )
    return all_text, pages, raw_parts


def read_pdf_pages(file_bytes, settings):
    pages = []
    raw_parts = []
    all_text = ""
    total_rects = 0
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        page_indexes = _parse_page_range(settings.get("page_range"), len(pdf.pages))
        for pi in page_indexes:
            page = pdf.pages[pi]
            text = (
                page.extract_text(
                    x_tolerance=settings.get("x_tolerance", 3),
                    y_tolerance=settings.get("y_tolerance", 3),
                )
                or ""
            )
            text = _strip_glyph_paren(_decode_cid(text))
            raw_parts.append(text)
            all_text += text + "\n"
            total_rects += len(page.rects)
            pages.append(
                {
                    "page_no": page.page_number,
                    "char_count": len(page.chars),
                    "line_count": len(page.lines),
                    "rect_count": len(page.rects),
                }
            )
    # pdfminer returns almost nothing for PDFs with a non-standard CID encoding
    # (e.g. MediVision Platinum's 'Adobe-UTF-8' collection) -- glyphs are embedded
    # but unmappable, so the file is misread as scanned/empty. PyMuPDF maps them
    # correctly. Fall back ONLY when pdfplumber produced almost no text AND the
    # recovered text names a producer we have a dedicated CID-aware parser for --
    # otherwise a coarse gate would just relabel an unparseable file (generic->…)
    # and break its baseline without gaining any rows. Every file pdfplumber already
    # reads (>200 chars) is untouched by construction.
    if len(all_text.strip()) < 200:
        try:
            mu_text, mu_pages, mu_raw = _extract_with_pymupdf(file_bytes, settings)
            low = mu_text.lower()
            recovered = any(sig in low for sig in _CID_FALLBACK_SIGNATURES)
            if recovered and len(mu_text.strip()) > max(500, len(all_text.strip()) * 3):
                return mu_text, mu_pages, mu_raw, 0
        except Exception:
            pass
    return all_text, pages, raw_parts, total_rects
