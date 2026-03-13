from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.collector.open_facts import OpenFactsLookupError, fetch_and_store_product
from app.models.company import Company
from app.models.database import ReadSession
from app.models.product import Product

router = APIRouter(prefix="/barcode", tags=["barcode"])
scan_router = APIRouter(tags=["scan"])


class ScanBarcodeRequest(BaseModel):
    barcode: str


def _validate_barcode(barcode: str) -> None:
    if len(barcode) != 13 or not barcode.isdigit():
        raise HTTPException(status_code=400, detail="barcode must be 13 digits")


def _build_response(product: Product, company: Company) -> dict:
    return {
        "status": "found",
        "product": {
            "barcode": product.barcode,
            "name": product.name,
            "open_facts_url": product.open_facts_url,
        },
        "company": {
            "id": company.id,
            "name": company.name,
            "ethical_score": company.ethical_score,
        },
    }


async def _get_local_product(barcode: str) -> tuple[Product, Company] | None:
    if ReadSession is None:
        raise HTTPException(status_code=500, detail="read database is not configured")

    async with ReadSession() as session:
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


async def _collect_product(barcode: str) -> dict:
    try:
        collected_product = await fetch_and_store_product(barcode)
    except OpenFactsLookupError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if collected_product is None:
        raise HTTPException(status_code=404, detail="product not found")

    return collected_product


@router.get("/{barcode}")
async def get_product_by_barcode(barcode: str):
    _validate_barcode(barcode)

    row = await _get_local_product(barcode)
    if row is None:
        raise HTTPException(status_code=404, detail="product not found")

    product, company = row
    return _build_response(product, company)


@router.post("/{barcode}/collect")
async def collect_product_by_barcode(barcode: str):
    _validate_barcode(barcode)

    row = await _get_local_product(barcode)
    if row is not None:
        product, company = row
        return _build_response(product, company)

    return await _collect_product(barcode)


@scan_router.post("/scan/barcode")
async def scan_barcode(payload: ScanBarcodeRequest):
    _validate_barcode(payload.barcode)

    row = await _get_local_product(payload.barcode)
    if row is not None:
        product, company = row
        return _build_response(product, company)

    return await _collect_product(payload.barcode)
