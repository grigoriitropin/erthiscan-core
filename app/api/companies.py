from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import get_optional_user_id
from app.cache import cache_get, cache_set
from app.models.company import Company
from app.models.database import ReadSession
from app.models.report import Report
from app.models.user import User
from app.models.vote import Vote

# ROUTER DEFINITION: Handles all requests related to company browsing and detailed profiles.
router = APIRouter(prefix="/companies", tags=["companies"])

# --- DATA SCHEMAS (Pydantic) ---


class CompanyItem(BaseModel):
    """Summary view of a company for the directory list."""

    id: int
    name: str
    ethical_score: float
    has_reports: bool
    report_count: int

    model_config = {"from_attributes": True}


class CompaniesResponse(BaseModel):
    """Paginated response containing a list of companies and metadata."""

    items: list[CompanyItem]
    total: int
    page: int
    pages: int


class SubReportItem(BaseModel):
    """Detailed view of a 'Challenge' (sub-report) with community voting stats."""

    id: int
    user_id: int
    text: str
    sources: list[str]
    author: str
    created_at: datetime
    true_count: int
    false_count: int
    user_vote: int | None = None


class ReportItem(BaseModel):
    """Detailed view of a top-level report, including its nested challenges."""

    id: int
    user_id: int
    text: str
    sources: list[str]
    author: str
    created_at: datetime
    ethical_count: int
    unethical_count: int
    user_vote: int | None = None
    sub_reports: list[SubReportItem] = []


class CompanyDetail(BaseModel):
    """Full profile of a company, including its complete hierarchical reporting tree."""

    id: int
    name: str
    ethical_score: float
    report_count: int
    reports: list[ReportItem]


# --- ENDPOINTS ---


@router.get("", response_model=CompaniesResponse)
async def list_companies(
    search: str = Query("", max_length=100),
    # SORTING PATTERN: Strict validation of sort parameters to prevent SQL injection.
    sort: str = Query(
        "reports_desc", pattern="^(reports_desc|score_desc|score_asc|name_asc|name_desc)$"
    ),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """
    COMPANY DIRECTORY: Fetches a paginated list of companies.

    LOGIC:
    1. CACHE CHECK: Uses Redis to store the results of specific search/sort/page combinations.
    2. FILTERING: Only companies with at least one report are shown by default to maintain data quality.
    3. FUZZY SEARCH: If 'search' is provided, it uses 'pg_trgm' similarity matching.
    4. PAGINATION: Calculates total pages and applies offset/limit to the DB query.
    """
    cache_key = f"companies:{search}:{sort}:{page}:{per_page}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return CompaniesResponse(**cached)

    async with ReadSession() as session:
        # BASE FILTER: Hide companies that haven't been 'vetted' by a report yet.
        base_filter = Company.top_level_report_count > 0
        query = select(Company).where(base_filter)
        count_query = select(func.count(Company.id)).where(base_filter)

        # FUZZY SEARCH: Uses the normalized name for typo-tolerant matching.
        if search:
            from app.collector.utils import python_normalize_name

            similarity = func.similarity(Company.name_normalized, python_normalize_name(search))
            query = query.where(similarity > 0.15)
            count_query = count_query.where(similarity > 0.15)

        # DYNAMIC SORTING:
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

        # TOTAL COUNT: Needed for pagination metadata on the frontend.
        total = (await session.execute(count_query)).scalar_one()
        pages = max(1, (total + per_page - 1) // per_page)

        # EXECUTION: Apply pagination and fetch models.
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await session.execute(query)
        companies = result.scalars().all()

    # MAPPING: Prepare the final response object.
    response = CompaniesResponse(
        items=[
            CompanyItem(
                id=c.id,
                name=c.name,
                ethical_score=c.ethical_score,
                has_reports=c.top_level_report_count > 0,
                report_count=c.top_level_report_count,
            )
            for c in companies
        ],
        total=total,
        page=page,
        pages=pages,
    )
    # POPULATE CACHE: TTL of 120s ensures a balance between speed and data freshness.
    await cache_set(cache_key, response.model_dump(), ttl=120)
    return response


@router.get("/{company_id}", response_model=CompanyDetail)
async def get_company(
    company_id: int,
    # OPTIONAL USER: If the user is logged in, we fetch their specific votes for each report.
    user_id: int | None = Depends(get_optional_user_id),
):
    """
    COMPANY PROFILE: Detailed data including the tree of ethical reports.

    COMPLEX QUERY LOGIC:
    1. TOP-LEVEL REPORTS: Fetches reports (depth 0) and aggregates ethical/unethical votes using JOINs.
    2. USER CONTEXT: If a user_id is present, checks which reports the user has already voted on.
    3. CHALLENGES (SUB-REPORTS): Fetches nested reports (depth 1) for all parent reports in one batch.
    4. AGGREGATION: Builds a hierarchical JSON structure for the frontend.
    """
    cache_key = f"company:{company_id}:u:{user_id or 0}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return CompanyDetail(**cached)

    async with ReadSession() as session:
        company = await session.get(Company, company_id)
        if company is None:
            raise HTTPException(status_code=404, detail="company not found")

        # FETCH REPORTS: Uses filtering to aggregate ethical and unethical vote counts.
        result = await session.execute(
            select(
                Report.id,
                Report.user_id,
                Report.text,
                Report.sources,
                Report.created_at,
                User.username,
                func.count().filter(Vote.value == 1).label("ethical_count"),
                func.count().filter(Vote.value == -1).label("unethical_count"),
            )
            .join(User, User.id == Report.user_id)
            .outerjoin(Vote, Vote.report_id == Report.id)
            .where(Report.company_id == company_id, Report.depth == 0)
            .group_by(Report.id, User.username)
            .order_by(Report.created_at.desc())
        )
        rows = result.all()

        report_ids = [r.id for r in rows]

        # VOTE LOOKUP: Identifies the current user's participation.
        user_votes = {}
        if user_id and report_ids:
            uv_result = await session.execute(
                select(Vote.report_id, Vote.value).where(
                    Vote.user_id == user_id, Vote.report_id.in_(report_ids)
                )
            )
            user_votes = {row.report_id: row.value for row in uv_result.all()}

        # FETCH SUB-REPORTS: Collects all 'challenges' for the current view.
        sub_reports_by_parent: dict[int, list[SubReportItem]] = {}
        if report_ids:
            sub_result = await session.execute(
                select(
                    Report.id,
                    Report.user_id,
                    Report.parent_id,
                    Report.text,
                    Report.sources,
                    Report.created_at,
                    User.username,
                    func.count().filter(Vote.value == 1).label("true_count"),
                    func.count().filter(Vote.value == -1).label("false_count"),
                )
                .join(User, User.id == Report.user_id)
                .outerjoin(Vote, Vote.report_id == Report.id)
                .where(
                    Report.company_id == company_id,
                    Report.depth == 1,
                    Report.parent_id.in_(report_ids),
                )
                .group_by(Report.id, User.username)
                .order_by(
                    Report.vote_sum.desc()
                )  # Sort sub-reports by their community trust level.
            )
            sub_rows = sub_result.all()

            sub_ids = [s.id for s in sub_rows]
            sub_user_votes = {}
            if user_id and sub_ids:
                suv_result = await session.execute(
                    select(Vote.report_id, Vote.value).where(
                        Vote.user_id == user_id, Vote.report_id.in_(sub_ids)
                    )
                )
                sub_user_votes = {row.report_id: row.value for row in suv_result.all()}

            # ORCHESTRATION: Group sub-reports by their parent ID for nesting.
            for s in sub_rows:
                sub_reports_by_parent.setdefault(s.parent_id, []).append(
                    SubReportItem(
                        id=s.id,
                        user_id=s.user_id,
                        text=s.text,
                        sources=s.sources,
                        author=s.username,
                        created_at=s.created_at,
                        true_count=s.true_count,
                        false_count=s.false_count,
                        user_vote=sub_user_votes.get(s.id),
                    )
                )

    # FINAL ASSEMBLY: Construct the complex CompanyDetail response.
    response = CompanyDetail(
        id=company.id,
        name=company.name,
        ethical_score=company.ethical_score,
        report_count=company.top_level_report_count,
        reports=[
            ReportItem(
                id=r.id,
                user_id=r.user_id,
                text=r.text,
                sources=r.sources,
                author=r.username,
                created_at=r.created_at,
                ethical_count=r.ethical_count,
                unethical_count=r.unethical_count,
                user_vote=user_votes.get(r.id),
                sub_reports=sub_reports_by_parent.get(r.id, []),
            )
            for r in rows
        ],
    )
    await cache_set(cache_key, response.model_dump(), ttl=120)
    return response
