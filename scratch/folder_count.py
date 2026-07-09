import sys, time
sys.path.insert(0, '.')
from pathlib import Path
from extractors.party_pdf.pdf_io import extract_pdf

folder = Path(r'D:/Devs/Reports/Data/New Data/26 June/party_wise-26 June/Pdf')
files = sorted(folder.rglob('*.pdf'))
ok, empty, errs = [], [], []
for i, f in enumerate(files, 1):
    try:
        t0 = time.time()
        res = extract_pdf(f.read_bytes())
        dt = time.time() - t0
        fmt = res.get('detected_format', '?')
        rows = res.get('parsed_rows', []) or []
        perr = res.get('parse_error')
        tag = 'OK ' if rows else ('ERR' if perr else 'EMP')
        print(f'[{i:3d}/{len(files)}] {tag} {len(rows):5d}r {dt:4.1f}s {fmt:26s} {f.name[:40]}', flush=True)
        if rows:
            ok.append((f.name, fmt, len(rows)))
        elif perr:
            errs.append((f.name, fmt, perr[:60]))
        else:
            empty.append((f.name, fmt))
    except Exception as e:
        print(f'[{i:3d}/{len(files)}] CRASH {f.name[:40]} :: {repr(e)[:60]}', flush=True)
        errs.append((f.name, 'CRASH', repr(e)[:60]))

print('\n========== SUMMARY ==========', flush=True)
print(f'TOTAL:       {len(files)}', flush=True)
print(f'EXTRACTING:  {len(ok)}', flush=True)
print(f'EMPTY:       {len(empty)}', flush=True)
print(f'ERRORS:      {len(errs)}', flush=True)
print('\n--- EMPTY (0 rows) ---', flush=True)
for n, fmt in empty:
    print(f'   {fmt:26s} {n[:48]}', flush=True)
print('\n--- ERRORS ---', flush=True)
for n, fmt, e in errs:
    print(f'   {fmt:20s} {n[:40]}  {e}', flush=True)
