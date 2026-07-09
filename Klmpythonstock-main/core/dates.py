"""Shared date normalization — the single place report dates become ISO.

Vendor reports print dates in Indian day-first order (``04/05/2026`` = 4 May).
Downstream consumers treat ambiguous slash dates as month-first — the edge
functions' ``dateOrNull`` uses JS ``new Date("04/05/2026")`` → April 5, and
day>12 becomes Invalid Date → NULL — which silently swapped day/month for an
entire report (all ``DD/05/2026`` rows landed as ``2026-DD-05``/NULL).

Normalising to ISO ``YYYY-MM-DD`` here, at the point dates leave the engine
(``core.canonical.enforce_schema`` applies it to every ``type == "date"``
canonical field on every route), removes the ambiguity for ALL layouts at once.

Rules:
* ``datetime``/``date`` objects (Excel date cells) → ``isoformat()`` — unambiguous.
* ISO strings ``YYYY-MM-DD[ HH:MM:SS]`` → date part kept as-is — unambiguous.
* Excel serial numbers (plausible range 20000–80000 ≈ years 1954–2118) →
  converted from the 1899-12-30 epoch — unambiguous.
* Month-name forms (``05-Jun-2026``, ``5 June 26``, ``Jun 5, 2026``) → parsed —
  unambiguous.
* All-numeric ``D/M/Y`` (also ``-`` or ``.`` separators, 2- or 4-digit year) →
  **day-first** (Indian convention). Only if day-first is impossible (second
  field > 12) is month-first used — that file was genuinely MM/DD.
* Anything unrecognised is returned unchanged — never invent or drop a date;
  the DB boundary nulls values it cannot parse.
"""

import datetime as _dt
import re

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?$")
_DMY_RE = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$")
_DAY_MON_RE = re.compile(r"^(\d{1,2})[ /\-.]([A-Za-z]{3,9})[ /\-.,]+(\d{2,4})$")
_MON_DAY_RE = re.compile(r"^([A-Za-z]{3,9})[ /\-.,]+(\d{1,2})[ /\-.,]+(\d{2,4})$")

# Excel 1900 date system: serial 1 = 1900-01-01, with the fictitious 1900-02-29
# absorbed by anchoring the epoch at 1899-12-30.
_EXCEL_EPOCH = _dt.date(1899, 12, 30)
_SERIAL_MIN, _SERIAL_MAX = 20000, 80000


def _year(raw):
    y = int(raw)
    if y < 100:
        y += 2000 if y < 70 else 1900
    return y


def _valid(y, m, d):
    try:
        return _dt.date(y, m, d)
    except ValueError:
        return None


def _month_no(name):
    return _MONTHS.get(name[:3].lower())


def to_iso_date(value):
    """Normalise a report date to an ISO ``YYYY-MM-DD`` string.

    Ambiguous numeric dates are day-first (Indian convention); unambiguous
    forms (ISO, date objects, Excel serials, month names) parse as-is.
    Unrecognised values are returned unchanged.
    """
    if value is None:
        return value
    if isinstance(value, _dt.datetime):
        return value.date().isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        n = float(value)
        if n.is_integer() and _SERIAL_MIN <= n <= _SERIAL_MAX:
            return (_EXCEL_EPOCH + _dt.timedelta(days=int(n))).isoformat()
        return value

    s = str(value).strip()
    if not s:
        return value

    m = _ISO_RE.match(s)
    if m:
        d = _valid(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d.isoformat() if d else value

    m = _DMY_RE.match(s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), _year(m.group(3))
        d = _valid(y, b, a)  # day-first: a=day, b=month
        if d is None and b > 12:
            d = _valid(y, a, b)  # day-first impossible → genuine MM/DD
        return d.isoformat() if d else value

    m = _DAY_MON_RE.match(s)
    if m:
        mon = _month_no(m.group(2))
        if mon:
            d = _valid(_year(m.group(3)), mon, int(m.group(1)))
            if d:
                return d.isoformat()
        return value

    m = _MON_DAY_RE.match(s)
    if m:
        mon = _month_no(m.group(1))
        if mon:
            d = _valid(_year(m.group(3)), mon, int(m.group(2)))
            if d:
                return d.isoformat()
        return value

    if s.isdigit() and _SERIAL_MIN <= int(s) <= _SERIAL_MAX:
        return (_EXCEL_EPOCH + _dt.timedelta(days=int(s))).isoformat()

    return value
