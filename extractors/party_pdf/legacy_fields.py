import re

FIELD_SYNONYMS = {
    "party_name": [
        "party",
        "customer",
        "customer name",
        "party name",
        "buyer",
        "account",
        "account name",
        "cust name",
        "cust",
    ],
    "area": [
        "area",
        "territory",
        "region",
        "city",
        "town",
        "location",
        "party area",
        "station",
    ],
    "product_name": [
        "product",
        "item",
        "item name",
        "particulars",
        "description",
        "product name",
        "d e s c r i p t i o n",
        "material",
        "name",
    ],
    "product_code": ["product code", "item code", "code", "product c", "sr", "sr no"],
    "qty": ["qty", "quantity", "sale qty", "bill qty", "sold qty"],
    "free_qty": [
        "free",
        "fqty",
        "sch qty",
        "scheme qty",
        "claim qty",
        "free qty",
        "free qt",
        "fre",
    ],
    "rate": [
        "rate",
        "price",
        "ptr",
        "sales rate",
        "p.t.r.",
        "p t r",
        "prate",
        "pur rate",
        "pur.rate",
        "purchase rate",
    ],
    "amount": [
        "amount",
        "value",
        "net amt",
        "taxable",
        "goods value",
        "goods valu",
        "sale amount",
        "net amount",
        "claim value",
        "net.amt",
    ],
    "mrp": ["mrp", "m.r.p.", "mrp amt"],
    "pack": ["pack", "packing", "unit", "uom"],
    "batch": ["batch", "batch no", "batch no.", "lot"],
    "discount": [
        "discount",
        "disc",
        "disc %",
        "prod.dis",
        "prod dis",
        "sch disc",
        "trade disc",
    ],
    "division": ["division", "company", "agency", "mf"],
    "taxable_value": ["taxable value", "taxable amt"],
    "gst_amount": [
        "gst",
        "gst amt",
        "gst amount",
        "igst",
        "cgst",
        "sgst",
        "tax amt",
        "tax amount",
    ],
    "hsn": ["hsn", "hsn code", "hsn/sac"],
    "invoice_no": [
        "bill no",
        "inv no",
        "invoice no",
        "bill ref",
        "invdmno",
        "inv/dm no",
        "invoice",
        "inv no.",
        "bill no.",
    ],
    "invoice_date": ["bill date", "inv date", "invoice date", "date", "inv. date"],
    "inv_type": ["inv type", "type", "inv/dm"],
    "pur_rate": ["cost", "value prate", "value(prate)"],
    "opening_qty": ["opening", "op qty", "opening stock", "op bal", "opening qty"],
    "closing_qty": ["closing", "cl qty", "closing stock", "cl bal", "closing qty"],
    "inward_qty": [
        "inward",
        "purchase",
        "receipt",
        "in qty",
        "pur qty",
        "purchase qty",
    ],
    "outward_qty": [
        "outward",
        "sales",
        "issue",
        "out qty",
        "sale qty",
        "sold",
        "issue qty",
    ],
    "opening_value": ["opening value", "op value"],
    "closing_value": ["closing value", "cl value"],
    "expiry": ["expiry", "exp", "exp date", "expiry date"],
}

def _norm(s):
    s = re.sub(r"[^a-z0-9\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def match_field(raw):
    normed = _norm(raw)
    if not normed:
        return None, "empty", 0.0
    for canon, syns in FIELD_SYNONYMS.items():
        for syn in syns:
            if normed == _norm(syn):
                return canon, "exact", 1.0
    for canon, syns in FIELD_SYNONYMS.items():
        for syn in syns:
            ns = _norm(syn)
            if len(ns) >= 3 and (ns in normed or normed in ns):
                return canon, "contains", 0.85
    nt = set(normed.split())
    best_c, best_s = None, 0.0
    for canon, syns in FIELD_SYNONYMS.items():
        for syn in syns:
            sc = _jaccard(nt, set(_norm(syn).split()))
            if sc > best_s:
                best_s = sc
                best_c = canon
    if best_s >= 0.6:
        return best_c, "jaccard", best_s
    return None, "none", 0.0


def map_columns(headers):
    mapping = {}
    used = set()
    all_m = [(raw, *match_field(raw)) for raw in headers]
    all_m.sort(key=lambda x: -x[3])
    for raw, c, m, conf in all_m:
        if c and c not in used:
            mapping[raw] = {"canon": c, "method": m, "confidence": conf}
            used.add(c)
        else:
            mapping[raw] = {"canon": None, "method": "unmapped", "confidence": 0.0}
    return mapping
