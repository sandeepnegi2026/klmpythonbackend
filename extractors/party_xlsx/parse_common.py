import re

import pandas as pd

from core.header_match import normalize

from extractors.party_xlsx.constants import SUBTOTAL_RE


def compact(value):
    return normalize(value).replace(" ", "")


def cell_text(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


# Leading honorifics that are part of the party NAME, never a party by themselves.
_TITLES = {"DR", "DR.", "M/S", "M/S.", "MS", "MR", "MR.", "MRS", "SHRI", "SMT", "PROF"}


def split_party_area(raw_party, band_brand=False):
    """Split a "PARTY[,/-]AREA" band into (party, area).

    Default (``band_brand=False``) is byte-identical to the historical behaviour:
    party=first comma segment / area=last; hyphen rfind-split when the tail is
    <=30 chars.

    ``band_brand=True`` is for layouts whose party is a brand/outlet/DOCTOR name in
    which a LEADING TITLE or an INTERNAL hyphen belongs to the name, not a name/area
    separator. It is deliberately NARROW so it never mangles an ordinary
    ``SHOP,CITY`` / ``SHOP NAME-CITY`` band:
      * comma: only when the FIRST segment is a bare title ("DR,DHRUVIN A.JOSHI,PATAN"
        -> name "DR,DHRUVIN A.JOSHI", area "PATAN"; "DR,MUKESH SONI" -> whole name).
        A non-title first segment ("GADHAVI MEDICAL STORES,BUS STAND ROAD,CITY") keeps
        the historical name=first / area=last split.
      * hyphen: only when the pre-hyphen fragment is very short (<=5 chars), i.e. a
        brand stub ("DEV-PUSHP...", "MEDI-24...", "ZYRA-PHARMACY..."); a full
        "SHOP NAME-CITY" (long left) still splits.
    """
    raw = raw_party.strip()
    if not raw:
        return "", ""
    if "," in raw:
        parts = [part.strip() for part in raw.split(",")]
        if band_brand and parts[0].rstrip(".").upper() in _TITLES:
            return (",".join(parts[:-1]), parts[-1]) if len(parts) > 2 else (raw, "")
        return parts[0], parts[-1]
    if "-" in raw:
        idx = raw.rfind("-")
        left, right = raw[:idx].strip(), raw[idx + 1 :].strip()
        if band_brand and len(left) <= 5:
            return raw, ""
        if right and len(right) <= 30:
            return left, right
    return raw, ""


def is_subtotal(text):
    return bool(text and SUBTOTAL_RE.search(text))


def is_numeric_qty(value):
    if not str(value).strip():
        return False
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return pd.notna(parsed)


def looks_like_date(value):
    text = cell_text(value)
    if not text:
        return False
    return bool(
        re.match(r"^\d{4}-\d{2}-\d{2}", text)
        or re.match(r"^\d{2}-\d{2}-\d{2}", text)
        or re.match(r"^\d{2}/\d{2}/\d{4}", text)
    )


def row_dict(headers, raw_row):
    record = {}
    for idx, header in enumerate(headers):
        record[str(header)] = raw_row[idx] if idx < len(raw_row) else ""
    return record


def label_value(raw_row, label_prefix):
    for idx, cell in enumerate(raw_row):
        text = cell_text(cell).lower().rstrip(" :")
        if text.startswith(label_prefix):
            for j in range(idx + 1, len(raw_row)):
                val = cell_text(raw_row[j])
                if val and not cell_text(raw_row[j]).lower().startswith(label_prefix):
                    return val
    return ""
