import asyncio
import json
import logging
import os

from aiokafka import AIOKafkaConsumer
from redis.exceptions import RedisError
from sqlalchemy import update

from app.cache import cache_delete_pattern, get_redis
from app.enricher.company_score import recalculate_company_score
from app.models.database import WriteSession
from app.models.report import Report
from app.models.vote import Vote

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- BACKGROUND WORKER ---
# This service runs as a separate Kubernetes deployment. It consumes events 
# from Kafka to perform heavy database operations asynchronously, keeping the 
# main API fast and responsive.

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka.erthiscan.svc.cluster.local:9092")


async def _should_recalc(company_id: int) -> bool:
    """
    SCORING DEDUPLICATION: 
    Recalculating a company's score is an expensive SQL operation. 
    We use a short-lived (60s) Redis lock to ensure that even if 1,000 people 
    vote simultaneously, we only trigger ONE recalculation.
    
    FAIL-OPEN: If Redis is down, we return True and recalculate anyway to 
    ensure data consistency at the cost of temporary CPU load.
    """
    r = await get_redis()
    if r is None:
        return True
    try:
        return bool(await r.set(f"score_recalc:{company_id}", "1", ex=60, nx=True))
    except RedisError:
        logger.warning("redis score_recalc dedup failed; recalculating anyway", exc_info=True)
        return True


async def handle_vote(data: dict) -> None:
    """
    VOTE PROCESSOR: 
    1. Persists the new vote to the database.
    2. Atomically increments the denormalized 'vote_sum' on the target report.
    3. Triggers a company score recalculation if the deduplication lock allows.
    4. Invalidates the cache pattern for the affected company.
    """
    async with WriteSession() as session:
        vote = Vote(
            report_id=data["report_id"],
            user_id=data["user_id"],
            value=data["value"],
        )
        session.add(vote)

        # Atomic update with .returning() to get company_id in a single round-trip.
        company_id = (
            await session.execute(
                update(Report)
                .where(Report.id == data["report_id"])
                .values(vote_sum=Report.vote_sum + data["value"])
                .returning(Report.company_id)
            )
        ).scalar_one()

        if await _should_recalc(company_id):
            await recalculate_company_score(session, company_id)

        await session.commit()

    # Clear cache patterns to ensure the new vote is reflected in API responses.
    await cache_delete_pattern(f"company:{company_id}*")
    await cache_delete_pattern("companies:*")
    await cache_delete_pattern("scan:*")
    logger.info("vote processed: report=%d user=%d value=%d", data["report_id"], data["user_id"], data["value"])


async def handle_report(data: dict) -> None:
    """
    REPORT PROCESSOR:
    1. Persists the new report or challenge.
    2. If it's a top-level report (depth=0), increments the company's report counter.
    3. Triggers a company score recalculation (reports change the base weight).
    4. Invalidates all related cache patterns.
    """
    async with WriteSession() as session:
        report = Report(
            company_id=data["company_id"],
            user_id=data["user_id"],
            parent_id=data.get("parent_id"),
            depth=data.get("depth", 0),
            text=data["text"],
            sources=data["sources"],
        )
        session.add(report)

        if report.depth == 0:
            # We only increment the count for main claims, not sub-report challenges.
            from app.models.company import Company
            await session.execute(
                update(Company)
                .where(Company.id == data["company_id"])
                .values(top_level_report_count=Company.top_level_report_count + 1)
            )

        if await _should_recalc(data["company_id"]):
            await recalculate_company_score(session, data["company_id"])

        await session.commit()

    await cache_delete_pattern(f"company:{data['company_id']}*")
    await cache_delete_pattern("companies:*")
    await cache_delete_pattern("scan:*")
    logger.info("report processed: company=%d user=%d", data["company_id"], data["user_id"])


HANDLERS = {
    "votes": handle_vote,
    "reports": handle_report,
}


async def main() -> None:
    """
    KAFKA CONSUMER LOOP: 
    - Subscribes to 'votes' and 'reports' topics.
    - Uses 'group_id' to enable Kafka's consumer group balancing; multiple worker 
      pods will automatically split the partitions between them for horizontal scaling.
    - auto_offset_reset='earliest': Ensures that if a worker crashes and restarts, 
      it picks up exactly where it left off without missing any events.
    """
    consumer = AIOKafkaConsumer(
        *HANDLERS.keys(),
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id="erthiscan-worker",
        value_deserializer=lambda v: json.loads(v),
        auto_offset_reset="earliest",
    )

    await consumer.start()
    logger.info("worker started, listening on topics: %s", list(HANDLERS.keys()))

    try:
        # INFINITE LOOP: Continuously polls Kafka for new messages.
        async for msg in consumer:
            handler = HANDLERS.get(msg.topic)
            if handler is None:
                continue
            try:
                # ROUTING: Dispatch the message to the appropriate handler based on topic.
                await handler(msg.value)
            except Exception:
                # ERROR ISOLATION: A failure in one message does NOT crash the worker.
                # We log the exception and move to the next message.
                logger.exception("failed to process message on topic=%s", msg.topic)
    finally:
        # CLEANUP: Ensure the consumer connection is closed on shutdown.
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())
