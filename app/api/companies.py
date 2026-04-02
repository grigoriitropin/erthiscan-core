from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func

from app.cache import cache_get, cache_set
from app.models.company import Company
from app.models.database import ReadSession
from app.models.report import Report
from app.models.user import User
from app.models.vote import Vote

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
    sort: str = Query("reports_desc", pattern="^(reports_desc|score_desc|score_asc|name_asc|name_desc)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    cache_key = f"companies:{search}:{sort}:{page}:{per_page}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return CompaniesResponse(**cached)

    async with ReadSession() as session:
        query = select(Company)
        count_query = select(func.count(Company.id))

        if search:
            pattern = "%" + "%".join(search.split()) + "%"
            query = query.where(Company.name.ilike(pattern))
            count_query = count_query.where(Company.name.ilike(pattern))

        match sort:
            case "reports_desc":
                query = query.order_by(Company.top_level_report_count.desc())
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

    response = CompaniesResponse(
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
    await cache_set(cache_key, response.model_dump(), ttl=120)
    return response


class ReportItem(BaseModel):
    id: int
    text: str
    sources: list[str]
    author: str
    created_at: datetime
    vote_sum: int


class CompanyDetail(BaseModel):
    id: int
    name: str
    ethical_score: float
    report_count: int
    reports: list[ReportItem]


@router.get("/{company_id}", response_model=CompanyDetail)
async def get_company(company_id: int):
    cache_key = f"company:{company_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return CompanyDetail(**cached)

    async with ReadSession() as session:
        company = await session.get(Company, company_id)
        if company is None:
            raise HTTPException(status_code=404, detail="company not found")

        result = await session.execute(
            select(
                Report.id,
                Report.text,
                Report.sources,
                Report.created_at,
                User.username,
                func.coalesce(func.sum(Vote.value), 0).label("vote_sum"),
            )
            .join(User, User.id == Report.user_id)
            .outerjoin(Vote, Vote.report_id == Report.id)
            .where(Report.company_id == company_id, Report.depth == 0)
            .group_by(Report.id, User.username)
        )
        rows = result.all()

    response = CompanyDetail(
        id=company.id,
        name=company.name,
        ethical_score=company.ethical_score,
        report_count=company.top_level_report_count,
        reports=[
            ReportItem(
                id=r.id,
                text=r.text,
                sources=r.sources,
                author=r.username,
                created_at=r.created_at,
                vote_sum=r.vote_sum,
            )
            for r in rows
        ],
    )
    await cache_set(cache_key, response.model_dump(), ttl=120)
    return response
