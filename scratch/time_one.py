import sys, time
sys.path.insert(0, 'scripts'); sys.path.insert(0, '.')
import batch_extract as be
from extractors.party_pdf.detect import detect_format
from extractors.party_pdf.registry import PARSERS

frag = sys.argv[1]
folder = be.Path(r'D:/Devs/Reports/Data/New Data/26 June/party_wise-26 June/Pdf')
f = [p for p in folder.rglob('*.pdf') if frag.lower() in p.name.lower()][0]
txt = be.get('party_pdf', str(f)).get('raw_text', '')
fmt = detect_format(txt, 0, 20)
print(f'{f.name[:42]} | chars={len(txt)} | fmt={fmt}', flush=True)
if fmt in PARSERS:
    t0 = time.time()
    H, rows = PARSERS[fmt](txt)
    print(f'  parsed {len(rows)} rows in {time.time()-t0:.2f}s', flush=True)
else:
    print('  (no parser for this fmt)', flush=True)
