from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select, func

from app.models.company import Company
from app.models.database import ReadSession

router = APIRouter(prefix="/companies", tags=["companies"])


class CompanyItem(BaseModel):
    id: int
    name: str
    ethical_score: float
    has_reports: bool

    model_config = {"from_attributes": True}


class CompaniesResponse(BaseModel):
    items: list[CompanyItem]
    total: int
    page: int
    pages: int


@router.get("", response_model=CompaniesResponse)
async def list_companies(
    search: str = Query("", max_length=100),
    sort: str = Query("score_desc", pattern="^(score_desc|score_asc|name_asc|name_desc)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    async with ReadSession() as session:
        query = select(Company)
        count_query = select(func.count(Company.id))

        if search:
            pattern = "%" + "%".join(search.split()) + "%"
            query = query.where(Company.name.ilike(pattern))
            count_query = count_query.where(Company.name.ilike(pattern))

        match sort:
            case "score_desc":
                query = query.order_by(Company.ethical_score.desc())
            case "score_asc":
                query = query.order_by(Company.ethical_score.asc())
            case "name_asc":
                query = query.order_by(Company.name.asc())
            case "name_desc":
                query = query.order_by(Company.name.desc())

        total = (await session.execute(count_query)).scalar_one()
        pages = max(1, (total + per_page - 1) // per_page)

        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await session.execute(query)
        companies = result.scalars().all()

    return CompaniesResponse(
        items=[
            CompanyItem(
                id=c.id,
                name=c.name,
                ethical_score=c.ethical_score,
                has_reports=c.top_level_report_count > 0,
            )
            for c in companies
        ],
        total=total,
        page=page,
        pages=pages,
    )
