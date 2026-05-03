from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.report import Report
from app.models.vote import Vote

SCORE_RECALCULATION_VOTE_THRESHOLD = 10


def normalize_ethical_score(raw_score: int) -> float:
    """
    SCORING NORMALIZATION: Converts an unbounded raw integer score into a
    bounded percentage between -100.0 and 100.0.
    The formula uses a logarithmic-style dampening '(abs(x) + 5)' so that the
    first few votes have a strong impact, but it becomes harder to reach extreme
    scores as the raw score grows, preventing manipulation.
    """
    if raw_score == 0:
        return 0.0

    return 100 * raw_score / (abs(raw_score) + 5)


def register_vote(company: Company) -> bool:
    """
    BATCHING OPTIMIZATION: Instead of recalculating the heavy SQL query for every single vote,
    we keep a 'pending_vote_count'. The worker only triggers a full recalculation
    when this threshold is reached, drastically reducing database load.
    """
    company.pending_vote_count += 1
    return company.pending_vote_count >= SCORE_RECALCULATION_VOTE_THRESHOLD


async def recalculate_company_score(session: AsyncSession, company_id: int) -> Company:
    """
    HIERARCHICAL SCORING ALGORITHM:
    This is the core logic of Erthiscan.
    1. Parent Weight: Sum of all votes (+1/-1) on a top-level report.
    2. Challenge Penalty: If a sub-report (challenge) gets positive votes, those
       positive votes are subtracted from the parent report's weight.
       (e.g., If a claim has 10 upvotes, but a challenge refuting it has 8 upvotes,
       the effective weight of the claim drops to 2).
    3. Total Raw Score: The sum of all 'effective weights' across all reports for the company.
    """
    # Step 1: vote_sum per top-level report
    # We group all votes associated with top-level reports (depth == 0) for this company.
    # The coalesce ensures that if a report has no votes, its sum defaults to 0.
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
    # First, we calculate the total sum of votes for each individual sub-report (depth == 1).
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

    # Next, we aggregate those sub-report scores by their parent_id.
    # The 'case' statement is crucial: we ONLY consider sub-reports that have a POSITIVE sum.
    # Negative sub-reports (unsuccessful challenges) do not add to the penalty.
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
    # Finally, we join the parent votes with their calculated penalties.
    # The effective weight for each parent report is (parent vote_sum - penalty).
    # We sum all these effective weights together to get the 'raw_score' for the entire company.
    totals = await session.execute(
        select(
            func.count(parent_votes.c.report_id),
            func.coalesce(
                func.sum(parent_votes.c.vote_sum - func.coalesce(sub_penalty.c.penalty, 0)),
                0,
            ),
        ).outerjoin(sub_penalty, sub_penalty.c.parent_id == parent_votes.c.report_id)
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
