import unicodedata

def python_normalize_name(name: str | None) -> str:
    if name is None:
        return ""
    
    # Lowercase and strip whitespace
    s = name.lower().strip()
    
    # Normalize to NFKD to separate characters from their accents
    # Filter out combining marks (accents)
    normalized = "".join(
        c for c in unicodedata.normalize('NFKD', s)
        if not unicodedata.combining(c)
    )
    
    return normalized
