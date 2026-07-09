import sys
sys.path.insert(0, '.')
from pathlib import Path
from extractors.party_pdf.pdf_io import _decode_cid
import pdfplumber, io

frag = sys.argv[1]
folder = Path(r'D:/Devs/Reports/Data/New Data/26 June/party_wise-26 June/Pdf')
f = [p for p in folder.rglob('*.pdf') if frag.lower() in p.name.lower()][0]
print('FILE:', f.name, flush=True)
with pdfplumber.open(io.BytesIO(f.read_bytes())) as pdf:
    nr = sum(len(p.rects) for p in pdf.pages)
    nl = sum(len(p.lines) for p in pdf.pages)
    txt = ''
    for p in pdf.pages:
        txt += _decode_cid(p.extract_text() or '') + '\n'
print(f'pages={len(pdf.pages)} n_rects={nr} n_lines={nl} chars={len(txt)}', flush=True)
print('=' * 70, flush=True)
print(txt[:2600], flush=True)
