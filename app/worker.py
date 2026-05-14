import asyncio
import json
import logging
import os

from aiokafka import AIOKafkaConsumer
from redis.exceptions import RedisError

from app.cache import get_redis
from app.enricher.company_score import recalculate_company_score
from app.models.database import WriteSession

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


async def handle_recalc_score(data: dict) -> None:
    company_id = data["company_id"]
    try:
        async with WriteSession() as session:
            if await _should_recalc(company_id):
                await recalculate_company_score(session, company_id)
            await session.commit()
    except Exception:
        logger.exception("recalc_score failed for company=%d", company_id)
    else:
        logger.info("recalc_score processed: company=%d", company_id)


HANDLERS = {
    "recalc_score": handle_recalc_score,
}


async def main() -> None:
    """
    KAFKA CONSUMER LOOP:
    - Subscribes to the 'recalc_score' topic.
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
