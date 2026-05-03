import json
import os

from aiokafka import AIOKafkaProducer

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka.erthiscan.svc.cluster.local:9092")

_producer: AIOKafkaProducer | None = None


async def get_producer() -> AIOKafkaProducer:
    """
    KAFKA PRODUCER MANAGER: Implements a singleton pattern for the async Kafka producer.
    Ensures that we maintain a single, persistent connection to the Kafka broker 
    (KRaft cluster) across all API requests. Events are automatically serialized to JSON.
    """
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        await _producer.start()
    return _producer


async def emit_vote(report_id: int, user_id: int, value: int) -> None:
    """
    EVENT EMISSION: Publishes a 'vote' event to the Kafka broker.
    This allows the main API endpoint to return a 202 Accepted immediately,
    offloading the heavy database operations and score recalculation to the worker.
    """
    producer = await get_producer()
    await producer.send("votes", {"report_id": report_id, "user_id": user_id, "value": value})


async def emit_report(company_id: int, user_id: int, text: str, sources: list[str], parent_id: int | None = None, depth: int = 0) -> None:
    """
    EVENT EMISSION: Publishes a 'report' event to the Kafka broker.
    Both new ethical claims (depth=0) and challenges (depth=1) flow through here
    to be processed asynchronously by the backend worker.
    """
    producer = await get_producer()
    await producer.send("reports", {
        "company_id": company_id,
        "user_id": user_id,
        "text": text,
        "sources": sources,
        "parent_id": parent_id,
        "depth": depth,
    })


async def close_producer() -> None:
    """
    GRACEFUL SHUTDOWN: Called during the FastAPI app's shutdown lifecycle
    to cleanly close the Kafka connection and flush any pending messages.
    """
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None
