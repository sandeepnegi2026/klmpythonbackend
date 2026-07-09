import sys, re
sys.path.insert(0, '.')
from pathlib import Path
from extractors.party_pdf.pdf_io import _decode_cid
import pdfplumber, io

EMPTIES = [
 "300301_ (90)_KESHARI", "a_DISA_ENTERPRISE", "AW_KANARA", "BERA TRADERS-6",
 "KLM P_SHREE_BALAJI", "KLM STATEMENT PDF_PRATHNA", "KLM STOCK STATEMENT MAY 26_SWASTIK",
 "klm11_ARCHI_MEDICAL", "KLM2_PATEL_MEDICAL", "PARTY WISE KLM_BHARAT_MEDICAL",
 "PARTY WISE SALES MAY 2026 KLM DERMACOR", "pdpdf_ANNAPURNA", "Product wise sale list (Combined)",
 "Product wise sale list For the period", "REPORT_7HW15I59A_S_M", "report_BAJAJ_CHEMIST",
 "report_KUSHAL_DISTRIBUTOR", "REPORT_PATHAK_PHARMA", "sale and stock klm_BHARAT",
 "SAMPLE INVOICE 1_TIRUMALA", "COSMOQ_[Sample]_KLM COSMOQ DIV STOCK", "PEDIA_[Sample]_KLM PEDIA MAY P_VIPIN",
]
folder = Path(r'D:/Devs/Reports/Data/New Data/26 June/party_wise-26 June/Pdf')
allf = list(folder.rglob('*.pdf'))
for frag in EMPTIES:
    matches = [p for p in allf if frag.lower() in p.name.lower()]
    if not matches:
        print(f'??? NO MATCH: {frag}', flush=True); continue
    f = matches[0]
    with pdfplumber.open(io.BytesIO(f.read_bytes())) as pdf:
        txt = ''.join(_decode_cid(p.extract_text() or '') + '\n' for p in pdf.pages)
    # grab the most telling header/title line
    low = txt.lower()
    sig = ''
    for kw in ['sales detail register','sales detail summary','product wise sale','stock statement',
               'party wise','partywise','tax invoice','invoice','itemwise','item wise','statement of account',
               'sales register','customer','area wise','company']:
        if kw in low:
            sig += kw + '|'
    head = ' '.join(txt.split()[:14])
    print(f'\n### {f.name[:46]}', flush=True)
    print(f'    chars={len(txt)} sig=[{sig}]', flush=True)
    print(f'    head: {head[:110]}', flush=True)
