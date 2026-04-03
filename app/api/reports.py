from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from app.api.deps import get_current_user_id
from app.cache import cache_delete_pattern, get_redis
from app.enricher.company_score import recalculate_company_score
from app.events import emit_report
from app.models.company import Company
from app.models.database import ReadSession, WriteSession
from app.models.report import Report
from app.models.user import User
from app.models.vote import Vote

router = APIRouter(prefix="/reports", tags=["reports"])


class CreateReportRequest(BaseModel):
    company_id: int
    text: str = Field(min_length=1, max_length=150)
    sources: list[str] = Field(min_length=1)
    parent_id: int | None = None


class VoteRequest(BaseModel):
    value: int = Field(ge=-1, le=1)


class VoteResponse(BaseModel):
    ethical_count: int
    unethical_count: int
    user_vote: int | None


class UserReportItem(BaseModel):
    id: int
    company_id: int
    company_name: str
    text: str
    vote_sum: int
    created_at: str

    model_config = {"from_attributes": True}


class UserProfile(BaseModel):
    user_id: int
    username: str
    report_count: int
    reports: list[UserReportItem]


@router.post("", status_code=202)
async def create_report(
    payload: CreateReportRequest,
    user_id: int = Depends(get_current_user_id),
):
    depth = 0
    if payload.parent_id is not None:
        async with ReadSession() as session:
            parent = await session.get(Report, payload.parent_id)
            if parent is None:
                raise HTTPException(status_code=404, detail="parent report not found")
            if parent.depth != 0:
                raise HTTPException(status_code=400, detail="can only reply to top-level reports")
            if parent.company_id != payload.company_id:
                raise HTTPException(status_code=400, detail="company mismatch")
            depth = 1

    await emit_report(
        company_id=payload.company_id,
        user_id=user_id,
        text=payload.text,
        sources=payload.sources,
        parent_id=payload.parent_id,
        depth=depth,
    )
    return {"status": "accepted"}


@router.post("/{report_id}/vote", response_model=VoteResponse)
async def vote_on_report(
    report_id: int,
    payload: VoteRequest,
    user_id: int = Depends(get_current_user_id),
):
    if payload.value not in (1, -1):
        raise HTTPException(status_code=400, detail="value must be 1 or -1")

    async with WriteSession() as session:
        report = await session.get(Report, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="report not found")

        existing = (
            await session.execute(
                select(Vote).where(Vote.report_id == report_id, Vote.user_id == user_id)
            )
        ).scalar_one_or_none()

        if existing is not None:
            if existing.value == payload.value:
                # Toggle off — remove vote
                await session.delete(existing)
                report.vote_sum -= payload.value
            else:
                # Switch vote
                existing.value = payload.value
                report.vote_sum += 2 * payload.value
        else:
            # New vote
            session.add(Vote(report_id=report_id, user_id=user_id, value=payload.value))
            report.vote_sum += payload.value

        r = await get_redis()
        recalc_key = f"score_recalc:{report.company_id}"
        if not await r.exists(recalc_key):
            await recalculate_company_score(session, report.company_id)
            await r.set(recalc_key, "1", ex=60)

        await session.commit()

        # Read updated counts
        counts = (
            await session.execute(
                select(
                    func.count().filter(Vote.value == 1),
                    func.count().filter(Vote.value == -1),
                )
                .where(Vote.report_id == report_id)
            )
        ).one()

        # Check current user vote
        current_vote = (
            await session.execute(
                select(Vote.value).where(Vote.report_id == report_id, Vote.user_id == user_id)
            )
        ).scalar_one_or_none()

    await cache_delete_pattern(f"company:{report.company_id}*")
    await cache_delete_pattern("companies:*")
    await cache_delete_pattern("scan:*")

    return VoteResponse(
        ethical_count=counts[0],
        unethical_count=counts[1],
        user_vote=current_vote,
    )


@router.get("/me", response_model=UserProfile)
async def get_my_profile(user_id: int = Depends(get_current_user_id)):
    async with ReadSession() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")

        result = await session.execute(
            select(
                Report.id,
                Report.company_id,
                Company.name.label("company_name"),
                Report.text,
                Report.vote_sum,
                Report.created_at,
            )
            .join(Company, Company.id == Report.company_id)
            .where(Report.user_id == user_id, Report.depth == 0)
            .order_by(Report.created_at.desc())
        )
        rows = result.all()

    return UserProfile(
        user_id=user.id,
        username=user.username,
        report_count=len(rows),
        reports=[
            UserReportItem(
                id=r.id,
                company_id=r.company_id,
                company_name=r.company_name,
                text=r.text,
                vote_sum=r.vote_sum,
                created_at=str(r.created_at),
            )
            for r in rows
        ],
    )
