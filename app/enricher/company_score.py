from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.report import Report
from app.models.vote import Vote

SCORE_RECALCULATION_VOTE_THRESHOLD = 10


def normalize_ethical_score(raw_score: int) -> float:
    if raw_score == 0:
        return 0.0

    return 100 * raw_score / (abs(raw_score) + 5)


def register_vote(company: Company) -> bool:
    company.pending_vote_count += 1
    return company.pending_vote_count >= SCORE_RECALCULATION_VOTE_THRESHOLD


async def recalculate_company_score(session: AsyncSession, company_id: int) -> Company:
    # Step 1: vote_sum per top-level report
    parent_votes = (
        select(
            Report.id.label("report_id"),
            func.coalesce(func.sum(Vote.value), 0).label("vote_sum"),
        )
        .outerjoin(Vote, Vote.report_id == Report.id)
        .where(Report.company_id == company_id, Report.depth == 0)
        .group_by(Report.id)
        .subquery()
    )

    # Step 2: penalty from sub-reports — sum of positive sub-report vote_sums per parent
    sub_votes = (
        select(
            Report.parent_id.label("parent_id"),
            func.coalesce(func.sum(Vote.value), 0).label("sub_vote_sum"),
        )
        .outerjoin(Vote, Vote.report_id == Report.id)
        .where(Report.company_id == company_id, Report.depth == 1)
        .group_by(Report.id, Report.parent_id)
        .subquery()
    )

    sub_penalty = (
        select(
            sub_votes.c.parent_id,
            func.coalesce(
                func.sum(case((sub_votes.c.sub_vote_sum > 0, sub_votes.c.sub_vote_sum), else_=0)),
                0,
            ).label("penalty"),
        )
        .group_by(sub_votes.c.parent_id)
        .subquery()
    )

    # Step 3: effective weight = vote_sum - penalty
    totals = await session.execute(
        select(
            func.count(parent_votes.c.report_id),
            func.coalesce(
                func.sum(parent_votes.c.vote_sum - func.coalesce(sub_penalty.c.penalty, 0)),
                0,
            ),
        )
        .outerjoin(sub_penalty, sub_penalty.c.parent_id == parent_votes.c.report_id)
    )
    top_level_report_count, raw_score = totals.one()

    company = await session.get(Company, company_id)
    if company is None:
        raise ValueError(f"company {company_id} not found")

    company.top_level_report_count = top_level_report_count
    company.ethical_score = normalize_ethical_score(raw_score)
    company.pending_vote_count = 0

    await session.flush()
    return company
