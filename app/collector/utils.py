from unidecode import unidecode


def python_normalize_name(name: str | None) -> str:
    """
    STRING NORMALIZATION: Converts strings to a common baseline for search comparison.
    1. Removes accents and special characters using 'unidecode' (e.g., 'Nestlé' -> 'Nestle').
    2. Converts all text to lowercase.
    3. Strips leading and trailing whitespace.
    """
    if name is None:
        return ""
    return unidecode(name).lower().strip()
