from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.cache import cache_get, cache_set
from app.collector.open_facts import display_company_name
from app.models.company import Company
from app.models.database import ReadSession
from app.models.product import Product

# ROUTER DEFINITIONS:
# - router: Handles direct barcode lookups (/barcode/{barcode}).
# - scan_router: Handles the scanning intent from the app (/scan/barcode).
router = APIRouter(prefix="/barcode", tags=["barcode"])
scan_router = APIRouter(tags=["scan"])


class ScanBarcodeRequest(BaseModel):
    """Payload for the scan endpoint, expecting a standard 13-digit EAN code."""
    barcode: str


def _validate_barcode(barcode: str) -> None:
    """
    DATA VALIDATION: Ensures the input string is a valid EAN-13 barcode.
    Throws a 400 Bad Request if the format is incorrect.
    """
    if len(barcode) != 13 or not barcode.isdigit():
        raise HTTPException(status_code=400, detail="barcode must be 13 digits")


def _build_response(product: Product, company: Company) -> dict:
    """
    RESPONSE BUILDER: Maps internal DB models to the API response format.
    - Sanitizes company names using 'display_company_name' to handle placeholder entries.
    - Aggregates product details and company ethical metadata for frontend consumption.
    """
    return {
        "status": "found",
        "product": {
            "barcode": product.barcode,
            "name": product.name,
            "open_facts_url": product.open_facts_url,
        },
        "company": {
            "id": company.id,
            "name": display_company_name(company.name),
            "ethical_score": company.ethical_score,
            "report_count": company.top_level_report_count,
        },
    }


async def _get_local_product(barcode: str) -> tuple[Product, Company] | None:
    """
    DB ABSTRACTION: Retrieves a product and its associated company from the READ replica.
    Uses an INNER JOIN between 'products' and 'companies' to fetch all data in a single query.
    """
    if ReadSession is None:
        raise HTTPException(status_code=500, detail="read database is not configured")

    async with ReadSession() as session:
        # QUERY: Fetch both the Product and the parent Company in one trip.
        result = await session.execute(
            select(Product, Company)
            .join(Company, Company.id == Product.company_id)
            .where(Product.barcode == barcode)
        )
        row = result.first()

    if row is None:
        return None

    product, company = row
    return product, company


@router.get("/{barcode}")
async def get_product_by_barcode(barcode: str):
    """
    DIRECT LOOKUP ENDPOINT: Fetch product info by barcode ID.
    Bypasses the application cache to ensure the most up-to-date database information is returned.
    Useful for data verification and management.
    """
    _validate_barcode(barcode)

    row = await _get_local_product(barcode)
    if row is None:
        raise HTTPException(status_code=404, detail="product not found")

    product, company = row
    return _build_response(product, company)


@scan_router.post("/scan/barcode")
async def scan_barcode(payload: ScanBarcodeRequest):
    """
    SCANNING ENDPOINT: Optimized for high-frequency mobile app usage.
    
    PERFORMANCE FLOW:
    1. VALIDATION: Quick check of the barcode format.
    2. CACHING: Check Redis for a recent lookup of this specific barcode (TTL: 5 minutes).
       This drastically reduces DB load during viral scanning events.
    3. RECOVERY: If the cache is cold, perform the DB join.
    4. POPULATE: Save the result back to Redis for subsequent requests.
    """
    _validate_barcode(payload.barcode)

    # DISTRIBUTED CACHE: Check Redis to avoid hitting the DB for popular products.
    cache_key = f"scan:{payload.barcode}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    # DATABASE FALLBACK: Perform the join if not found in cache.
    row = await _get_local_product(payload.barcode)
    if row is not None:
        product, company = row
        response = _build_response(product, company)
        
        # WARM UP CACHE: Store the result for 300 seconds.
        await cache_set(cache_key, response, ttl=300)
        return response

    raise HTTPException(status_code=404, detail="product not found")
