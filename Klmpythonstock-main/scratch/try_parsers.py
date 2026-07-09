import sys
sys.path.insert(0, '.')
from pathlib import Path
from extractors.party_pdf.pdf_io import _decode_cid
from extractors.party_pdf.registry import PARSERS
import pdfplumber, io

frag = sys.argv[1]
names = sys.argv[2:]  # parser names to try
folder = Path(r'D:/Devs/Reports/Data/New Data/26 June/party_wise-26 June/Pdf')
f = [p for p in folder.rglob('*.pdf') if frag.lower() in p.name.lower()][0]
with pdfplumber.open(io.BytesIO(f.read_bytes())) as pdf:
    txt = ''.join(_decode_cid(p.extract_text() or '') + '\n' for p in pdf.pages)
print('FILE:', f.name[:55], flush=True)
for nm in names:
    if nm not in PARSERS:
        print(f'  {nm:28s} -- NOT A PARSER', flush=True); continue
    try:
        H, rows = PARSERS[nm](txt)
        print(f'  {nm:28s} -> {len(rows)} rows | headers={H}', flush=True)
        for r in rows[:3]:
            print(f'       {r}', flush=True)
    except Exception as e:
        print(f'  {nm:28s} -> ERROR {repr(e)[:70]}', flush=True)
