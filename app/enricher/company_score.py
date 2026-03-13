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


def should_recalculate_after_report(company: Company) -> bool:
    return company.top_level_report_count == 0


def register_vote(company: Company) -> bool:
    company.pending_vote_count += 1
    return company.pending_vote_count >= SCORE_RECALCULATION_VOTE_THRESHOLD


async def recalculate_company_score(session: AsyncSession, company_id: int) -> Company:
    vote_sum = func.coalesce(func.sum(Vote.value), 0)
    report_weight = func.greatest(1, 1 + vote_sum)
    report_contribution = case(
        (Report.type == "positive", report_weight),
        else_=-report_weight,
    )

    report_scores = (
        select(
            Report.id.label("report_id"),
            report_contribution.label("contribution"),
        )
        .outerjoin(Vote, Vote.report_id == Report.id)
        .where(Report.company_id == company_id, Report.depth == 0)
        .group_by(Report.id, Report.type)
        .subquery()
    )

    totals = await session.execute(
        select(
            func.count(report_scores.c.report_id),
            func.coalesce(func.sum(report_scores.c.contribution), 0),
        )
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
