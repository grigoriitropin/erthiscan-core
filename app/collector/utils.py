from unidecode import unidecode


def python_normalize_name(name: str | None) -> str:
    if name is None:
        return ""
    return unidecode(name).lower().strip()
