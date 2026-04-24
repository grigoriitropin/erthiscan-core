NO_INFORMATION = "No information"
MISSING_COMPANY_NAME_PREFIX = "__missing_company__:"


def normalize_product_name(product_name: str | None) -> str:
    if product_name is None:
        return NO_INFORMATION

    stripped = product_name.strip()
    return stripped or NO_INFORMATION


def normalize_company_name(company_name: str | None, barcode: str) -> str:
    if company_name is None:
        return f"{MISSING_COMPANY_NAME_PREFIX}{barcode}"

    stripped = company_name.strip()
    if not stripped:
        return f"{MISSING_COMPANY_NAME_PREFIX}{barcode}"

    return stripped


def display_company_name(company_name: str) -> str:
    if company_name.startswith(MISSING_COMPANY_NAME_PREFIX):
        return NO_INFORMATION

    return company_name
