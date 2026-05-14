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


async def emit_recalc_score(company_id: int) -> None:
    """
    EVENT EMISSION: Publishes a 'recalc_score' event to the Kafka broker.
    Used after lightweight synchronous API operations (like voting or deleting a report)
    to offload the heavy database score recalculation and cache invalidation to the worker.
    """
    producer = await get_producer()
    await producer.send("recalc_score", {"company_id": company_id})


async def close_producer() -> None:
    """
    GRACEFUL SHUTDOWN: Called during the FastAPI app's shutdown lifecycle
    to cleanly close the Kafka connection and flush any pending messages.
    """
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None
