import json
import os

from aiokafka import AIOKafkaProducer

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka.erthiscan.svc.cluster.local:9092")

_producer: AIOKafkaProducer | None = None


async def get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        await _producer.start()
    return _producer


async def emit_vote(report_id: int, user_id: int, value: int) -> None:
    producer = await get_producer()
    await producer.send("votes", {"report_id": report_id, "user_id": user_id, "value": value})


async def emit_report(company_id: int, user_id: int, text: str, sources: list[str], parent_id: int | None = None, depth: int = 0) -> None:
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
    global _producer
    if _producer is not None:
        await _producer.stop()
        _producer = None
