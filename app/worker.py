import asyncio
import json
import logging
import os

from aiokafka import AIOKafkaConsumer
from sqlalchemy import update

from app.cache import cache_delete_pattern, get_redis
from app.enricher.company_score import recalculate_company_score
from app.models.database import WriteSession
from app.models.report import Report
from app.models.vote import Vote

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka.erthiscan.svc.cluster.local:9092")


async def handle_vote(data: dict) -> None:
    async with WriteSession() as session:
        vote = Vote(
            report_id=data["report_id"],
            user_id=data["user_id"],
            value=data["value"],
        )
        session.add(vote)

        company_id = (
            await session.execute(
                update(Report)
                .where(Report.id == data["report_id"])
                .values(vote_sum=Report.vote_sum + data["value"])
                .returning(Report.company_id)
            )
        ).scalar_one()

        r = await get_redis()
        recalc_key = f"score_recalc:{company_id}"
        if await r.set(recalc_key, "1", ex=60, nx=True):
            await recalculate_company_score(session, company_id)

        await session.commit()

    await cache_delete_pattern(f"company:{company_id}*")
    await cache_delete_pattern("companies:*")
    await cache_delete_pattern("scan:*")
    logger.info("vote processed: report=%d user=%d value=%d", data["report_id"], data["user_id"], data["value"])


async def handle_report(data: dict) -> None:
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
            from app.models.company import Company
            await session.execute(
                update(Company)
                .where(Company.id == data["company_id"])
                .values(top_level_report_count=Company.top_level_report_count + 1)
            )

        r = await get_redis()
        recalc_key = f"score_recalc:{data['company_id']}"
        if await r.set(recalc_key, "1", ex=60, nx=True):
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
        async for msg in consumer:
            handler = HANDLERS.get(msg.topic)
            if handler is None:
                continue
            try:
                await handler(msg.value)
            except Exception:
                logger.exception("failed to process message on topic=%s", msg.topic)
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())
