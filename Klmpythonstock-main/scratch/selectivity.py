import sys, re
sys.path.insert(0, '.')
from pathlib import Path
from extractors.party_pdf.pdf_io import _decode_cid
from extractors.party_pdf.detect import detect_format
from extractors.party_pdf.registry import PARSERS
import pdfplumber, io

folder = Path(r'D:/Devs/Reports/Data/New Data/26 June/party_wise-26 June/Pdf')
matches = []
for f in sorted(folder.rglob('*.pdf')):
    with pdfplumber.open(io.BytesIO(f.read_bytes())) as pdf:
        nr = sum(len(p.rects) for p in pdf.pages)
        nl = sum(len(p.lines) for p in pdf.pages)
        txt = ''.join(_decode_cid(p.extract_text() or '') + '\n' for p in pdf.pages)
    tl = txt[:2000].lower()
    # CANDIDATE NEW SIGNAL:
    hit = ("party / item wise" in tl) and ("d e s c r i p t i o n" in tl)
    if hit:
        cur_fmt = detect_format(txt, nr, nl)
        rows = 0
        if cur_fmt in PARSERS:
            try:
                rows = len(PARSERS[cur_fmt](txt)[1])
            except Exception:
                rows = -1
        matches.append((f.name[:46], cur_fmt, rows))

print(f'SIGNAL MATCHES {len(matches)} files:')
for n, fmt, r in matches:
    flag = '  <-- WORKING! DO NOT STEAL' if r > 0 else ''
    print(f'   curfmt={fmt:18s} curRows={r:5d}  {n}{flag}')
