import re


def extract_party_and_area(raw_party, fmt):
    raw = raw_party.strip()
    if not raw:
        return ("", "")
    if fmt == "technomax_free_qty":
        raw = re.sub(r'(?:[,\s]+(?:AHMEDABAD|AMADAVAD)[.\s]*)+$', '', raw, flags=re.IGNORECASE).strip()
        raw = re.sub(r',[.\s]*R-\d+[.\s]*$', '', raw, flags=re.IGNORECASE).strip()
        raw = raw.rstrip('.,* ')
        
        # Check for parenthesis at the end
        m = re.match(r'^(.+?)\s*\(([^)]+)\)[.\s]*$', raw)
        if m:
            name = m.group(1).strip()
            area = m.group(2).strip()
            return name, area
            
        words = raw.split()
        if words and words[0].upper().startswith('DR.'):
            if len(words) >= 2:
                return ' '.join(words[:2]), ' '.join(words[2:])
        elif words and words[0].upper() == 'DR':
            if len(words) >= 3:
                return ' '.join(words[:3]), ' '.join(words[3:])
                
        suffixes = [
            r'STORES?', r'MEDICALS?', r'PHARMAC(?:Y|IES|Y?)', r'CHEMIST',
            r'MEDICINES?', r'MEDICINS?', r'CLINICS?', r'SHOPS?',
            r'STORS?', r'AGENC(?:Y|IES)', r'DISTR\.PRA\.LIT\.', r'DISTR\b',
            r'LIFE\s+CARE', r'AESTHETICS', r'MEDICOS?',
            r'TRADERS?', r'DISTRIBUTORS?', r'ENTERPRISES?',
            r'DUKAN', r'DAVA', r'HEALTHCARE'
        ]
        pattern = r'\b(' + '|'.join(suffixes) + r')(?:(?=\W)|$)([-.\s]*\d+)?'
        
        matches = list(re.finditer(pattern, raw, flags=re.IGNORECASE))
        if matches:
            last_match = matches[-1]
            end_idx = last_match.end()
            name = raw[:end_idx].strip()
            area = raw[end_idx:].strip()
            
            # Clean area
            area = re.sub(r'^[-,\s.*]+', '', area).strip()
            
            # If area starts with a parenthesis like (YASH FLORA), shift it back to the name
            m_area = re.match(r'^(\([^)]+\))\s*(.*)$', area)
            if m_area:
                name = name + ' ' + m_area.group(1)
                area = m_area.group(2).strip()
                area = re.sub(r'^[-,\s.*]+', '', area).strip()
                
            area_words = area.split()
            if len(area_words) == 2 and area_words[0].upper() == area_words[1].upper():
                area = area_words[0]
                
            return name, area
            
        if len(words) >= 2:
            return ' '.join(words[:-1]), words[-1]
            
        return raw, ''
    if fmt in ("marg_summary", "custom_pharma", "marg_register"):
        parts = [p.strip() for p in raw.split(",")]
        return (parts[0], parts[-1]) if len(parts) >= 2 else (raw, "")
    if fmt == "unisolve":
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            return ("", "")
        name = parts[0]
        area = parts[-1] if len(parts) >= 2 else ""
        
        # Strip BETUL and parentheses around it from name
        name = re.sub(r"\s*\(\s*BETUL\.?\s*\)", "", name, flags=re.IGNORECASE).strip()
        name = re.sub(r"\s*\bBETUL\b\.?", "", name, flags=re.IGNORECASE).strip()
        name = name.rstrip(",- ")
        
        # Clean area spelling typos
        area = re.sub(r"\bSTAIND\b", "STAND", area, flags=re.IGNORECASE)
        area = re.sub(r"\bROA\b", "ROAD", area, flags=re.IGNORECASE)
        area = re.sub(r"\bMANDIRE\b", "MANDIR", area, flags=re.IGNORECASE)
        area = area.strip()
        
        return (name, area)
    if fmt == "marg_bordered":
        if "=" in raw:
            p = raw.split("=", 1)
            return (p[0].strip(), re.sub(r"\s*[><]+$", "", p[1]).strip())
        return (raw, "")
    if fmt == "logic_erp":
        parts = [p.strip() for p in raw.split(',')]
        IGNORE_KEYWORDS = {
            'WEEKLY', 'ADV LOCAL', 'TEJAL', 'CASH', 'CO CUS', '15_DAYS', '10_DAYS', 
            'DOCTOR', 'ADVANCE OUTSTATION', 'HOSMRVSNU', 'JAIMIN', 'ADVANCE'
        }
        
        field0 = parts[0].strip()
        field1 = parts[1].strip() if len(parts) >= 2 else ''
        field1_up = field1.upper()
        
        has_explicit_area = False
        explicit_area = ''
        if field1 and field1_up not in IGNORE_KEYWORDS and not re.match(r'^\d+$', field1):
            has_explicit_area = True
            explicit_area = field1
            
        name = field0
        area = ''
        
        if '--' in field0:
            idx = field0.find('--')
            name = field0[:idx].strip()
            area = field0[idx+2:].strip()
        elif ' - ' in field0:
            idx = field0.rfind(' - ')
            name = field0[:idx].strip()
            area = field0[idx+3:].strip()
        elif '-' in field0:
            idx = field0.rfind('-')
            possible_area = field0[idx+1:].strip()
            if len(possible_area) >= 3 and not possible_area.upper() in {'BRANCH', 'LTD', 'PVT', '2', '3', 'NEW'}:
                name = field0[:idx].strip()
                area = possible_area
                
        if has_explicit_area:
            area = explicit_area
                
        if not area:
            for p in parts[1:]:
                p_clean = p.strip()
                p_up = p_clean.upper()
                if p_clean and p_up not in IGNORE_KEYWORDS and not p_up.startswith('VADODARA') and not p_up == 'OUT STATION' and not p_up == 'ADV LOCAL':
                    area = p_clean
                    break
                    
        if ',' in field0:
            subparts = [sp.strip() for sp in field0.split(',')]
            name = subparts[0]
            area = subparts[-1]
            
        name = name.rstrip(',- /')
        name = re.sub(r'[,\s]+(?:CO CUS|Cash)\b.*$', '', name, flags=re.IGNORECASE).strip()
        
        if area and name.upper().endswith(area.upper()):
            name = name[:len(name)-len(area)].strip().rstrip(',- /')
            if name.upper().endswith(' NEW'):
                name = name[:-4].strip().rstrip(',- /')
                area = 'NEW ' + area
                
        return name, area
    if fmt == "wep_legacy":
        raw = re.sub(r"\(cid:\d+\)", "", raw).strip()
        parts = [p.strip() for p in raw.split("-") if p.strip()]
        if len(parts) >= 2:
            name = parts[0]
            area = ""
            for p in reversed(parts[1:]):
                cleaned = re.sub(r"\d{3,6}\s*$", "", p).strip()
                if cleaned and not cleaned.isdigit():
                    area = cleaned
                    break
            return (name, area)
        return (raw, "")
    if fmt == "busy_tally":
        name, area = raw, ""
        # Store-word suffixes that anchor the party/area split. Includes common
        # Busy/Tally misspellings & truncations: STORS=STORES, STOR/STO=STORE.
        _SUFFIXES = {
            "STORE", "STORES", "STORS", "STOR", "STO",
            "MEDICOSE", "MEDICOS", "MEDICAL", "MEDICALS",
            "PHARMA", "PHARMACY", "AGENCY", "AGENCIES", "HALL", "DEPOT",
            "ENTERPRISE", "ENTERPRISES", "TRADER", "TRADERS", "DISTRIBUTORS",
            "SUPPLIER", "SUPPLIERS", "CHEMIST",
        }
        if "-" in raw:
            idx = raw.rfind("-")
            name, area = raw[:idx].strip(), raw[idx + 1 :].strip()
            # Jodhpur/SIDDHI convention: "<NAME>-<CITY>-L[.]" carries a trailing
            # bare "L"/"L." locality tag AFTER the real city. rfind() grabs the
            # tag as the area and buries the city in the name; promote the city
            # instead. Tightly guarded (tail is exactly L/L., and a hyphenated
            # alpha city precedes it) so single-tail "<NAME>-<AREACODE>" bands —
            # incl. the Gwalior L->LASHKAR mapping below — stay untouched.
            if area.rstrip(".").upper() == "L" and "-" in name:
                j = name.rfind("-")
                city = name[j + 1 :].strip()
                if re.fullmatch(r"[A-Za-z][A-Za-z .]{2,}", city) and (
                    city.rstrip(".").upper() not in _SUFFIXES
                ):
                    name, area = name[:j].strip(), city
        else:
            words = raw.split()
            if len(words) >= 2 and words[-1].rstrip(".").upper() not in _SUFFIXES:
                for i in range(len(words) - 2, -1, -1):
                    if words[i].rstrip(".").upper() in _SUFFIXES:
                        name, area = " ".join(words[: i + 1]), " ".join(words[i + 1 :])
                        break
            # NOTE: deliberately NO generic "trailing word = city" fallback here.
            # It corrupts suffix-less names whose last token is a surname
            # (e.g. "DR.NITIN GUPTA" -> area "GUPTA"). Splitting a trailing city
            # off such headings needs a location gazetteer, not a lexical guess.

        # Clean area if it joined suffix and shop number e.g. STORE6/10/2
        m_suff = re.match(r"^(STORE|STORES|PHARMACY|MEDICAL|MEDICOSE|MEDICOS|AGENCY|AGENCIES)([\d/\s.-]+)$", area, flags=re.IGNORECASE)
        if m_suff:
            name = name + " " + m_suff.group(1)
            area = m_suff.group(2).strip()
            
        # Translate short area abbreviations to their full names
        _AREA_MAP = {
            "L": "LASHKAR",
            "LA": "LASHKAR",
            "LAS": "LASHKAR",
            "LASH": "LASHKAR",
            "MOR": "MORAR",
            "GWALI": "GWALIOR",
            "SHIV": "SHIVPURI",
        }
        area = _AREA_MAP.get(area.upper(), area)
        
        return (name, area)
    if fmt == "marg_sale_details":
        words = raw.split()
        if len(words) >= 3:
            last = words[-1]
            if last[0].isupper() and last.lower() not in (
                "pvt",
                "ltd",
                "pvt.ltd.",
                "stores",
                "store",
                "medical",
                "pharmacy",
                "medicose",
                "hospital",
                "agencies",
            ):
                return (" ".join(words[:-1]), last)
        return (raw, "")
    if fmt == "marg_bordered_billwise":
        m = re.match(r"^(.+?)\.\((\w+)\)?", raw)
        if m:
            return (m.group(1).strip(), m.group(2).strip())
        m = re.match(r"^(.+?)\s*\(([\w.]+)$", raw)
        if m:
            return (m.group(1).strip(), m.group(2).strip())
        m = re.match(r"^(.+?)\(([\w.]+)\)$", raw)
        if m:
            return (m.group(1).strip(), m.group(2).strip())
        _SUFFIXES = {
            "STORE",
            "STORES",
            "STO",
            "STOR",
            "MEDICAL",
            "MEDICINE",
            "MEDICINES",
            "MEDICO",
            "PHARMACY",
            "PHARMACIES",
            "CHEMIST",
            "CLINIC",
            "CLINI",
            "CARE",
            "HOME",
            "LIFE",
            "AGENCY",
            "AGE",
            "DEPOT",
            "AESTHETICS",
            "ENTERPRISE",
            "HALL",
        }
        _TRUNC = {"AGE", "STO", "STOR", "SAL", "CLINI", "MEDI", "NANP", "KA", "GO", "A", "K"}
        words = raw.rstrip(".").split()
        if len(words) >= 2:
            last = words[-1]
            last_up = last.upper()
            prev_up = words[-2].upper()
            if last_up in _TRUNC and prev_up in _SUFFIXES:
                return (raw.rstrip("."), "")
            if (
                re.match(r"^[A-Z0-9.]{2,4}$", last_up)
                and last_up not in _SUFFIXES
            ):
                if words[0].startswith("DR.") and len(last) <= 3:
                    return (" ".join(words[:-1]), last)
                if prev_up in _SUFFIXES:
                    return (" ".join(words[:-1]), last)
        return (raw.rstrip("."), "")
    if fmt == "product_party_wise_list":
        return split_gujarat_party_area(raw)
    return (raw, "")


# --------------------------------------------------------------------------- #
# Gujarat/Surat party -> (name, area) split for Marg "Product + Party Wise List"
# headings, where the area is embedded in the heading in three shapes:
#   NAME(AREA) | NAME (CLINIC/DR) AREA | NAME <STORE-SUFFIX> AREA
# and, for DR. headings with a bare trailing area, a location gazetteer — because
# a lexical "last word = area" guess would turn a surname into an area
# (DR.MANOJ KANSARA -> "KANSARA"). The gazetteer grows as new files arrive.
# --------------------------------------------------------------------------- #
_GJ_AREAS = {
    "KATARGAM", "ADAJAN", "VARACHA", "VARACHHA", "WARACHA", "NANAVARACHA",
    "SARTHANA", "ATHVA", "ANKLESWAR", "BHARUCH", "RANDER", "UDHNA", "UMRA",
    "PIPLOD", "VESU", "PAL", "PALANPUR", "PALANPORE", "KAMREJ", "KOSAMBA",
    "AMROLI", "LALGATE", "BHATAR", "SIMADA", "MANGROL", "CHIKUVADI",
    "JAHAGIRABAD", "SALTHANA", "BAPS", "OLPAD",
}
_GJ_AREA_PHRASES = [
    "MOTA VARACHA", "MOTA VARACHHA", "MOTA WARACHA", "NANA VARACHHA",
    "LAL DARWAJA", "LAL DARVAJA", "JAKAT NAKA", "SARTHANA JAKATNAKA",
    "PALANPUR PATIYA", "KATHODRA GAM", "RING ROAD", "PAL ROAD", "OLPAD ROAD",
    "A K ROAD", "L.H ROAD", "L.H.ROAD",
]
# a trailing token ending in one of these is a location, gazetteer or not
_AREA_TAIL = re.compile(r"(ROAD|GAM|NAGAR|NAKA|PATIYA|CHOWK|DARWAJA|DARVAJA|GATE)$", re.I)
_STORE_SUFFIX = re.compile(
    r"\b(STORES?|MEDICALS?|MEDICOSE?|MEDICOS?|PHARMAC(?:Y|IES)|CHEMIST|"
    r"AGENC(?:Y|IES)|ENTERPRISES?|DISTRIBUTORS?|TRADERS?|HALL|DEPOT|"
    r"CLINIC|HEALTHCARE|AESTHETICS)\b",
    re.I,
)
# a parenthesis holding a doctor/clinic descriptor is NOT an area
_CLINIC_PAREN = re.compile(r"CLINIC|HOSPITAL|SKIN|HAIR|LASER|COSMETIC|AESTHETIC|CARE|^DR\.?\b", re.I)
_LEGAL_TAIL = re.compile(r"^(PVT|LTD|P\.?V\.?T|L\.?T\.?D|LLP)[.\s]*", re.I)


def split_gujarat_party_area(raw):
    s = re.sub(r"\s+", " ", raw or "").strip().rstrip(".")
    if not s:
        return "", ""

    # 1) parentheses -----------------------------------------------------------
    parens = list(re.finditer(r"\(([^)]*)\)", s))
    if parens:
        last = parens[-1]
        trail = s[last.end():].strip(" .-,")
        if trail and not re.search(r"\d", trail):        # "(clinic/dr) AREA"
            return s[: last.end()].strip(" .-,"), trail
        inner = last.group(1).strip()
        if not trail and inner and not _CLINIC_PAREN.search(inner):  # "NAME(AREA)"
            name = (s[: last.start()] + s[last.end():]).strip(" .-,")
            return name, inner
        # else: paren is a doctor/clinic name -> keep on the name, fall through

    # 2) store-suffix anchored (word[s] after STORE/PHARMACY/MEDICAL/...) -------
    ms = list(_STORE_SUFFIX.finditer(s))
    if ms:
        area = re.sub(r"\([^)]*\)", "", s[ms[-1].end():]).strip(" .-,")
        if area and not _LEGAL_TAIL.match(area):
            return s[: ms[-1].end()].strip(" .-,"), area

    # 3) hyphen-joined trailing area: "NAME-AREA" ------------------------------
    if "-" in s:
        head, _, tail = s.rpartition("-")
        tail = tail.strip(" .,()")
        if tail.upper() in _GJ_AREAS or _AREA_TAIL.search(tail):
            return head.strip(" .-,"), tail

    # 4) gazetteer / location-tail trailing (safe for DR. surnames) ------------
    up = s.upper()
    for phrase in sorted(_GJ_AREA_PHRASES, key=len, reverse=True):
        if up.endswith(" " + phrase):
            return s[: len(s) - len(phrase)].strip(" .-,"), s[len(s) - len(phrase):].strip()
    words = s.split()
    if len(words) >= 2:
        last_w = words[-1].strip(".,")
        if last_w.upper() in _GJ_AREAS or _AREA_TAIL.search(last_w):
            return " ".join(words[:-1]).strip(" .-,"), last_w

    return s, ""
