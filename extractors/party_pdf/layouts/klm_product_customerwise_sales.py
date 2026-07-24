import io
import re
from collections import defaultdict

import pdfplumber

# BALAJI ENTERPRISES / SUMAN PHARMA "Product-Customer Wise Sales".
#
# Product-grouped (product header 'KL...'), then per-customer rows:
#   <CUSTOMER NAME> <STATION> <Qty> <Free> <Sales Value> [<Pin>]
# Name/Station split on the station column x-boundary (~190). The numeric block
# (x0>=350) ends in the Sales Value decimal; the ints before it are Qty, Free.
# Per-product 'TOTAL' + 'GRAND TOTAL' are the oracles; sum(Amount) reconciles EXACT.
# Positional: re-opens the PDF bytes.

_X_STATION = 190.0
_X_NUM = 350.0
_DEC = re.compile(r"^-?\d[\d,]*\.\d+$")
_INT = re.compile(r"^-?\d[\d,]*$")
_PROD_RE = re.compile(r"^KL[A-Z]?\d")
_TOTAL_RE = re.compile(r"^TOTAL\s+-?\d")
_GRAND_RE = re.compile(r"^GRAND TOTAL\s+-?\d")
_SKIP_PREFIX = ("Page No.", "Customer Station", "KLM LABORATORIES",
                "BALAJI ENTERPRISES", "SUMAN", "247,BLOCK", "Powered By")
_STN_SUFFIX = ("KOLKATA", "HOWRAH", "BELIAGHATA", "MADHYAMGRAM")


def _num(s):
    return float(s.replace(",", ""))


def _split_name_station(ws):
    name_parts, stn_parts = [], []
    for w in ws:
        t = w["text"]
        if w["x1"] <= _X_STATION:
            name_parts.append(t)
        elif w["x0"] >= _X_STATION:
            stn_parts.append(t)
        else:
            cut = None
            for suf in _STN_SUFFIX:
                i = t.find(suf)
                if i > 0:
                    cut = i
                    break
            if cut is not None:
                name_parts.append(t[:cut])
                stn_parts.append(t[cut:])
            else:
                name_parts.append(t)
    return " ".join(name_parts).strip(), " ".join(stn_parts).strip()


def parse_klm_product_customerwise_sales(text, file_bytes=None):
    headers = ["Party Name", "Area", "Product Name", "Qty", "Free", "Amount"]
    rows = []
    if not file_bytes:
        return headers, rows
    cur_prod = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines = defaultdict(list)
            for w in page.extract_words(use_text_flow=False):
                lines[round(w["top"])].append(w)
            for top in sorted(lines):
                ws = sorted(lines[top], key=lambda x: x["x0"])
                s = " ".join(w["text"] for w in ws).strip()
                if (not s or s.startswith("----") or s.replace("*", "") == ""
                        or s.startswith("...Continued") or s.startswith(_SKIP_PREFIX)):
                    continue
                if _GRAND_RE.match(s) or _TOTAL_RE.match(s):
                    continue
                if _PROD_RE.match(s):
                    cur_prod = s
                    continue
                num_w = [w["text"] for w in ws if w["x0"] >= _X_NUM]
                dec_idx = next((i for i, t in enumerate(num_w) if _DEC.match(t)), None)
                if dec_idx is None:
                    continue
                amount = _num(num_w[dec_idx])
                ints = [t for t in num_w[:dec_idx] if _INT.match(t)]
                qty = _num(ints[0]) if len(ints) >= 1 else 0.0
                free = _num(ints[1]) if len(ints) >= 2 else 0.0
                party, station = _split_name_station(ws)
                rows.append([party, station, cur_prod, qty, free, amount])
    return headers, rows
