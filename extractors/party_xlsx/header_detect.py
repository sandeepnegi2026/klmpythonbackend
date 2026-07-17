from core.header_match import match_header


def detect_header_row(rows, hint=None, min_matches=3):
    if hint:
        idx = max(0, int(hint) - 1)
        return idx if idx < len(rows) else None
    for idx, row in enumerate(rows[:150]):
        matched_keys = {match_header(cell, "party")[0] for cell in row}
        matched_keys.discard(None)
        if len(matched_keys) >= min_matches:
            return idx
    return None
