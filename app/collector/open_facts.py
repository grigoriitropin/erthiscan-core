# CONSTANTS for handling missing data during the Open Food Facts import process.
NO_INFORMATION = "No information"
# Prefix used to generate a unique placeholder name for companies missing from the source data.
# This prevents products without companies from colliding under a single empty company name.
MISSING_COMPANY_NAME_PREFIX = "__missing_company__:"


def normalize_product_name(product_name: str | None) -> str:
    """
    DATA CLEANING: Ensures product names are valid strings.
    If the name is missing or empty, returns a standardized placeholder.
    """
    if product_name is None:
        return NO_INFORMATION

    stripped = product_name.strip()
    return stripped or NO_INFORMATION


def normalize_company_name(company_name: str | None, barcode: str) -> str:
    """
    DATA CLEANING: Handles missing company names during import.
    If a product has no brand/company listed, we generate a unique placeholder
    based on the product's barcode (e.g., '__missing_company__:1234567890123').
    This ensures the database schema (which requires a unique company name) is satisfied
    without wrongly grouping unrelated products under one 'Unknown' company.
    """
    if company_name is None:
        return f"{MISSING_COMPANY_NAME_PREFIX}{barcode}"

    stripped = company_name.strip()
    if not stripped:
        return f"{MISSING_COMPANY_NAME_PREFIX}{barcode}"

    return stripped


def display_company_name(company_name: str) -> str:
    """
    UI FORMATTING: Used by the API endpoints to hide the ugly internal placeholder
    names (like '__missing_company__:123') from the frontend, replacing them with
    a clean 'No information' string.
    """
    if company_name.startswith(MISSING_COMPANY_NAME_PREFIX):
        return NO_INFORMATION

    return company_name
