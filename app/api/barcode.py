from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.models.company import Company
from app.models.database import ReadSession
from app.models.product import Product

router = APIRouter(prefix="/barcode", tags=["barcode"])


@router.get("/{barcode}")
async def get_product_by_barcode(barcode: str):
    if len(barcode) != 13 or not barcode.isdigit():
        raise HTTPException(status_code=400, detail="barcode must be 13 digits")

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
        raise HTTPException(status_code=404, detail="product not found")

    product, company = row

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
