import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from redis.exceptions import RedisError
from sqlalchemy import delete, func, select, update

from app.api.deps import get_current_user_id
from app.cache import cache_delete_pattern, get_redis
from app.enricher.company_score import recalculate_company_score
from app.events import emit_report
from app.models.company import Company
from app.models.database import ReadSession, WriteSession
from app.models.report import Report
from app.models.user import User
from app.models.vote import Vote

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


# --- DATA SCHEMAS (Pydantic) ---

class CreateReportRequest(BaseModel):
    """Payload for submitting a new ethical claim or a challenge."""
    company_id: int
    text: str = Field(min_length=1, max_length=150)
    sources: list[str] = Field(min_length=1)
    # If parent_id is provided, this becomes a depth=1 'challenge' to an existing report.
    parent_id: int | None = None


class UpdateReportRequest(BaseModel):
    text: str = Field(min_length=1, max_length=150)
    sources: list[str] = Field(min_length=1)


class VoteRequest(BaseModel):
    """Payload for voting. 1 = True/Ethical, -1 = False/Unethical."""
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
    sources: list[str]
    vote_sum: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UserChallengeItem(BaseModel):
    id: int
    parent_id: int
    company_id: int
    company_name: str
    text: str
    sources: list[str]
    vote_sum: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UserProfile(BaseModel):
    """Profile data showing a user's contributions to the platform."""
    user_id: int
    username: str
    report_count: int
    challenge_count: int
    reports: list[UserReportItem]
    challenges: list[UserChallengeItem]


# --- ENDPOINTS ---

@router.post("", status_code=202)
async def create_report(
    payload: CreateReportRequest,
    user_id: int = Depends(get_current_user_id),
):
    """
    CREATE REPORT: Submits a new claim.
    
    ASYNC ARCHITECTURE: 
    This endpoint returns 202 Accepted immediately after validating the input 
    and pushing an event to Kafka. The actual database insertion and score 
    recalculation happens asynchronously in 'worker.py'.
    """
    # VALIDATION: Ensure the target company exists.
    async with ReadSession() as session:
        company = await session.get(Company, payload.company_id)
        if company is None:
            raise HTTPException(status_code=404, detail="company not found")

    depth = 0
    # HIERARCHY VALIDATION: If replying to an existing report.
    if payload.parent_id is not None:
        async with ReadSession() as session:
            parent = await session.get(Report, payload.parent_id)
            if parent is None:
                raise HTTPException(status_code=404, detail="parent report not found")
            # We only allow one level of nesting (challenges to main reports).
            if parent.depth != 0:
                raise HTTPException(status_code=400, detail="can only reply to top-level reports")
            # Prevent associating a challenge with a different company than its parent.
            if parent.company_id != payload.company_id:
                raise HTTPException(status_code=400, detail="company mismatch")
            depth = 1

    # EVENT EMISSION: Send the validated payload to the Kafka broker.
    await emit_report(
        company_id=payload.company_id,
        user_id=user_id,
        text=payload.text,
        sources=payload.sources,
        parent_id=payload.parent_id,
        depth=depth,
    )
    return {"status": "accepted"}


@router.patch("/{report_id}")
async def update_report(
    report_id: int,
    payload: UpdateReportRequest,
    user_id: int = Depends(get_current_user_id),
):
    """
    UPDATE REPORT: Allows authors to edit their text/sources.
    """
    async with WriteSession() as session:
        report = await session.get(Report, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="report not found")
        # SECURITY: Ensure only the author can modify the report.
        if report.user_id != user_id:
            raise HTTPException(status_code=403, detail="not your report")

        report.text = payload.text
        report.sources = payload.sources
        company_id = report.company_id
        await session.commit()

    # CACHE INVALIDATION: Clear all relevant caches that might display the old report data.
    await cache_delete_pattern(f"company:{company_id}*")
    await cache_delete_pattern("companies:*")
    await cache_delete_pattern("scan:*")
    return {"status": "updated"}


@router.delete("/{report_id}")
async def delete_report(
    report_id: int,
    user_id: int = Depends(get_current_user_id),
):
    """
    DELETE REPORT: Safely removes a report and its cascade dependencies.
    """
    async with WriteSession() as session:
        report = await session.get(Report, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="report not found")
        if report.user_id != user_id:
            raise HTTPException(status_code=403, detail="not your report")

        company_id = report.company_id
        was_top_level = report.depth == 0

        # CASCADE DELETION: If a top-level report is deleted, we must also 
        # delete all its sub-reports (challenges) and all associated votes.
        if was_top_level:
            # Find sub-report ids first, then delete their votes and the sub-reports
            sub_ids_result = await session.execute(
                select(Report.id).where(Report.parent_id == report_id)
            )
            sub_ids = [row[0] for row in sub_ids_result.all()]
            if sub_ids:
                # Delete votes on sub-reports
                await session.execute(delete(Vote).where(Vote.report_id.in_(sub_ids)))
                # Delete the sub-reports themselves
                await session.execute(delete(Report).where(Report.id.in_(sub_ids)))

        # Delete votes on the main report, then the report itself.
        await session.execute(delete(Vote).where(Vote.report_id == report_id))
        await session.delete(report)
        await session.flush()

        # RECALCULATE: Deleting a report changes the company's ethical score.
        await recalculate_company_score(session, company_id)
        await session.commit()

    # CACHE INVALIDATION
    await cache_delete_pattern(f"company:{company_id}*")
    await cache_delete_pattern("companies:*")
    await cache_delete_pattern("scan:*")
    return {"status": "deleted"}


@router.post("/{report_id}/vote", response_model=VoteResponse)
async def vote_on_report(
    report_id: int,
    payload: VoteRequest,
    user_id: int = Depends(get_current_user_id),
):
    """
    VOTING LOGIC: Handles the complex logic of adding, changing, or removing a vote.
    """
    if payload.value not in (1, -1):
        raise HTTPException(status_code=400, detail="value must be 1 or -1")

    async with WriteSession() as session:
        # LOCKING: with_for_update prevents race conditions if multiple people vote simultaneously.
        report = await session.get(Report, report_id, with_for_update=True)
        if report is None:
            raise HTTPException(status_code=404, detail="report not found")

        # Check if the user has already voted.
        existing = (
            await session.execute(
                select(Vote).where(Vote.report_id == report_id, Vote.user_id == user_id)
            )
        ).scalar_one_or_none()

        if existing is not None:
            # TOGGLE: If voting the same value again, remove the vote entirely.
            if existing.value == payload.value:
                await session.delete(existing)
                delta = -payload.value
            # CHANGE: If flipping vote from 1 to -1 (or vice versa), apply a delta of 2.
            else:
                existing.value = payload.value
                delta = 2 * payload.value
        else:
            # NEW VOTE
            session.add(Vote(report_id=report_id, user_id=user_id, value=payload.value))
            delta = payload.value

        # Update the denormalized vote_sum column for performance.
        await session.execute(
            update(Report).where(Report.id == report_id).values(vote_sum=Report.vote_sum + delta)
        )

        # DE-DUPLICATION (Fail-open): 
        # Scoring recalculation is heavy. We use a short-lived Redis lock to ensure 
        # that a flood of simultaneous votes on the same company only triggers ONE recalculation.
        should_recalc = False
        r = await get_redis()
        if r is not None:
            try:
                # 'nx=True' ensures this only returns True for the FIRST request within 60s.
                should_recalc = bool(
                    await r.set(f"score_recalc:{report.company_id}", "1", ex=60, nx=True)
                )
            except RedisError:
                # FAIL-OPEN: If Redis is down, we recalculate anyway. 
                # It's better to waste CPU cycles than to leave the score out of sync.
                logger.warning("redis score_recalc dedup failed; recalculating anyway", exc_info=True)
                should_recalc = True
        else:
            should_recalc = True
            
        if should_recalc:
            await recalculate_company_score(session, report.company_id)

        await session.commit()

        # Read updated counts to return to the frontend for immediate UI updates.
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

    # Invalidate all caches related to this company and search results.
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
    """
    USER PROFILE: Aggregates all reports and challenges created by the authenticated user.
    """
    async with ReadSession() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="user not found")

        # Fetch top-level reports
        reports_result = await session.execute(
            select(
                Report.id,
                Report.company_id,
                Company.name.label("company_name"),
                Report.text,
                Report.sources,
                Report.vote_sum,
                Report.created_at,
            )
            .join(Company, Company.id == Report.company_id)
            .where(Report.user_id == user_id, Report.depth == 0)
            .order_by(Report.created_at.desc())
        )
        report_rows = reports_result.all()

        # Fetch sub-reports (challenges)
        challenges_result = await session.execute(
            select(
                Report.id,
                Report.parent_id,
                Report.company_id,
                Company.name.label("company_name"),
                Report.text,
                Report.sources,
                Report.vote_sum,
                Report.created_at,
            )
            .join(Company, Company.id == Report.company_id)
            .where(Report.user_id == user_id, Report.depth == 1)
            .order_by(Report.created_at.desc())
        )
        challenge_rows = challenges_result.all()

    return UserProfile(
        user_id=user.id,
        username=user.username,
        report_count=len(report_rows),
        challenge_count=len(challenge_rows),
        reports=[
            UserReportItem(
                id=r.id,
                company_id=r.company_id,
                company_name=r.company_name,
                text=r.text,
                sources=r.sources,
                vote_sum=r.vote_sum,
                created_at=r.created_at,
            )
            for r in report_rows
        ],
        challenges=[
            UserChallengeItem(
                id=c.id,
                parent_id=c.parent_id,
                company_id=c.company_id,
                company_name=c.company_name,
                text=c.text,
                sources=c.sources,
                vote_sum=c.vote_sum,
                created_at=c.created_at,
            )
            for c in challenge_rows
        ],
    )
