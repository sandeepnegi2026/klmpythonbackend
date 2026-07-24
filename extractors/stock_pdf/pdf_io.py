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


# --- TT-glyph-index subset decode (SURANA DRUG DISTRIBUTORS print-captures) ---
# Twin of the decoder in extractors/party_pdf/pdf_io.py, wired here for the STOCK
# route. Some PCL/GDI print-to-PDF captures embed subset fonts whose /Encoding
# /Differences names are raw TrueType glyph indices ("/g22") with NO ToUnicode
# CMap. pdfminer then emits '(cid:N)' for codes < 32 (which _decode_cid turns into
# control-char garbage) and identity WinAnsi chars for codes >= 32, so the whole
# document is unreadable although it renders perfectly -- and detect_layout never
# sees "saleablestockreport"/"(q+f)", dropping the file to 0 rows. The original
# face is the PCL-resident Monotype font whose glyph order is fixed (3=space,
# 4..29=A..Z, 131..156=a..z, 613='0', 616..624='1'..'9', punctuation below incl.
# 683='+'), so the text is fully recoverable: char code -> /gN name -> glyph index
# -> char. The decode is attempted only when the already-extracted text is drowning
# in control chars (_looks_gid_garbled: >=500 of them AND >=25% of all chars; the
# worst normal corpus file has 11) and is ADOPTED only when the decoded text
# contains one of _TTGID_SIGNATURES, i.e. a header detect_layout already routes. A
# gid-subset PDF from another producer whose font has a different glyph order fails
# the >1%-unknown guard or the signature test and stays exactly as garbled as
# before -- so this fallback can never relabel any other file.
# NOTE: the SURANA Saleable Stock Report's May export ships a ToUnicode map (reads
# cleanly and never reaches this branch); only the June export dropped it.
_TTGID_SIGNATURES = ("saleable stock report",)

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
    683: "+",
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
    # Gid-subset print-captures (see _decode_gid_differences above): a font with NO
    # ToUnicode whose /Differences are raw /gN glyph indices. pdfplumber then yields
    # long control-char garbage -- so the <200-char MediVision gate above never fires
    # -- detect_layout misses "saleablestockreport"/"(q+f)", and the file drops 0 rows.
    # The gate is structural (text drowning in control chars) and adoption additionally
    # requires a known-parseable signature in the decoded text, so every file the
    # branch does not fire for is byte-for-byte unaffected.
    if _looks_gid_garbled(all_text):
        try:
            decoded = _decode_gid_differences(file_bytes)
            if decoded:
                dec_pages, _ = decoded
                # _decode_gid_differences decodes every page; keep only the pages this
                # call extracted (respect settings["page_range"]) so all_text/raw_parts
                # stay aligned with `pages`.
                sel = [dec_pages[i] for i in page_indexes if i < len(dec_pages)]
                dec_full = "".join(pt + "\n" for pt in sel)
                if any(sig in dec_full.lower() for sig in _TTGID_SIGNATURES):
                    raw_parts = sel
                    all_text = dec_full
                    for meta, ptext in zip(pages, sel):
                        meta["char_count"] = len(ptext)
        except Exception:
            pass
    return all_text, pages, raw_parts, total_rects
