import httpx
from sqlalchemy.dialects.postgresql import insert

from app.models.company import Company
from app.models.database import WriteSession
from app.models.product import Product

OPEN_FACTS_PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
NO_INFORMATION = "No information"
MISSING_COMPANY_NAME_PREFIX = "__missing_company__:"


class OpenFactsLookupError(Exception):
    pass


def _extract_product_name(product_data: dict) -> str | None:
    return (
        product_data.get("product_name_en")
        or product_data.get("product_name")
        or product_data.get("generic_name_en")
        or product_data.get("generic_name")
    )


def _extract_company_name(product_data: dict) -> str | None:
    brand_owner = product_data.get("brand_owner")
    if brand_owner:
        return brand_owner.strip()

    brands = product_data.get("brands")
    if not brands:
        return None

    first_brand = brands.split(",", maxsplit=1)[0].strip()
    return first_brand or None


def _build_open_facts_url(host: str | None, barcode: str) -> str | None:
    if not host:
        return None

    return f"https://{host}/product/{barcode}"


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


async def store_product(
    barcode: str,
    product_name: str | None,
    company_name: str | None,
    open_facts_url: str | None,
) -> dict:
    if WriteSession is None:
        raise OpenFactsLookupError("write database is not configured")

    stored_product_name = normalize_product_name(product_name)
    stored_company_name = normalize_company_name(company_name, barcode)

    async with WriteSession() as session:
        company_insert = insert(Company).values(name=stored_company_name)
        company_result = await session.execute(
            company_insert.on_conflict_do_update(
                index_elements=[Company.name],
                set_={"name": company_insert.excluded.name},
            ).returning(Company.id, Company.name, Company.ethical_score)
        )
        company_id, persisted_company_name, ethical_score = company_result.one()

        product_insert = insert(Product).values(
            barcode=barcode,
            name=stored_product_name,
            company_id=company_id,
            open_facts_url=open_facts_url,
        )
        product_result = await session.execute(
            product_insert.on_conflict_do_update(
                index_elements=[Product.barcode],
                set_={
                    "name": product_insert.excluded.name,
                    "company_id": product_insert.excluded.company_id,
                    "open_facts_url": product_insert.excluded.open_facts_url,
                },
            ).returning(Product.barcode, Product.name, Product.open_facts_url)
        )
        stored_barcode, stored_product_name, stored_open_facts_url = product_result.one()

        await session.commit()

        return {
            "status": "found",
            "product": {
                "barcode": stored_barcode,
                "name": stored_product_name,
                "open_facts_url": stored_open_facts_url,
            },
            "company": {
                "id": company_id,
                "name": display_company_name(persisted_company_name),
                "ethical_score": ethical_score,
            },
        }


async def fetch_and_store_product(barcode: str) -> dict | None:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(
                OPEN_FACTS_PRODUCT_URL.format(barcode=barcode),
                params={"product_type": "all"},
                headers={
                    "User-Agent": "ErthiscanCore/0.1",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise OpenFactsLookupError("open facts request failed") from exc

    payload = response.json()
    if payload.get("status") != 1:
        return None

    product_data = payload.get("product") or {}
    product_name = _extract_product_name(product_data)
    company_name = _extract_company_name(product_data)
    open_facts_url = _build_open_facts_url(response.url.host, barcode)

    return await store_product(barcode, product_name, company_name, open_facts_url)
