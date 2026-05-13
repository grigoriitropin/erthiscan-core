# erthiscan-core

Erthiscan Core API: A high-performance, asynchronous FastAPI backend for the ethical company scoring platform.

## Overview

Erthiscan Core is the central intelligence unit of the Erthiscan project. It enables users to identify the parent companies behind products by scanning barcodes (EAN-13), view crowdsourced "ethical reports," and participate in a hierarchical voting system that determines a company's ethical score.

## Key Features

- **Barcode Intelligence**: Lookup 13-digit EAN barcodes to identify products and their parent organizations.
- **Hierarchical Reporting**: Supports top-level ethical reports and nested "challenges" (sub-reports) to provide nuance to corporate behavior.
- **Dynamic Scoring**: A sophisticated scoring algorithm that calculates company ratings based on crowdsourced votes and report weights.
- **Advanced Search**: High-performance company search using PostgreSQL `pg_trgm` similarity.
- **Event-Driven Architecture**: Uses Kafka to decouple API requests from heavy data processing and scoring recalculations.
- **Resilient Caching**: Distributed caching and locking using Redis to ensure high throughput and data consistency.

## Technical Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.14+)
- **Asynchronous IO**: `asyncio` with [uvicorn](https://www.uvicorn.org/)
- **Database**: [PostgreSQL](https://www.postgresql.org/) with [SQLAlchemy](https://www.sqlalchemy.org/) (Async) and [asyncpg](https://magicstack.github.io/asyncpg/)
- **Migrations**: [Alembic](https://alembic.sqlalchemy.org/)
- **Message Broker**: [Apache Kafka](https://kafka.apache.org/) via [aiokafka](https://aiokafka.readthedocs.io/)
- **Cache & Locks**: [Redis](https://redis.io/) (with `hiredis` support)
- **Observability**: [Prometheus](https://prometheus.io/) metrics and [structlog](https://www.structlog.org/) JSON logging
- **Validation**: [Pydantic v2](https://docs.pydantic.dev/)
- **Authentication**: Google OAuth2 (JWT-based)

## Project Structure

- `app/`: Primary application source.
    - `api/`: REST API endpoints (Auth, Barcode, Companies, Reports).
    - `collector/`: Data normalization and external integration (e.g., Open Food Facts).
    - `enricher/`: Core scoring logic and data aggregation algorithms.
    - `models/`: Database schemas (SQLAlchemy) and data transfer objects (Pydantic).
    - `main.py`: API entry point, middleware, and lifecycle management.
    - `worker.py`: Kafka consumer for asynchronous event processing.
- `alembic/`: Database schema versioning.
- `tests/`: Comprehensive unit and integration test suite.

## Data Flow & Scoring (Hybrid Architecture)

To provide immediate UI feedback while handling heavy computation, Erthiscan uses a hybrid event-driven approach:

1. **Reports (Async)**: Creating a new report emits an event to Kafka. The API returns 202 Accepted immediately. The `worker.py` consumes it, persists to DB, and triggers score recalculation.
2. **Votes & Mutations (Synchronous + Eventual Consistency)**: Voting, updating, or deleting a report synchronously mutates the database to provide instant feedback to the user. Then, it emits a lightweight `recalc_score` event to Kafka.
3. **Processing**: The `worker.py` service consumes events and performs heavy operations asynchronously.
4. **Scoring Logic**: Recalculates the company score using a hierarchical weight system. Positive votes on a "challenge" (sub-report) act as a penalty to the parent report's weight.
5. **Consistency & Resilience**: Redis distributed locks ensure that scoring recalculations for the same company don't overlap (60s dedup). If Kafka goes down, the API degrades gracefully (fail-open) to ensure votes are still recorded.

## Development

### Setup (using `uv`)

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Run database migrations
alembic upgrade head

# Start the API server
uv run uvicorn app.main:app --reload
```

### Quality Control

```bash
# Run tests
pytest

# Linting & Formatting
ruff check .
ruff format .
mypy .
```

## Deployment

The service is containerized using the provided `Dockerfile` and is designed to run in Kubernetes environments with separate Read and Write database endpoints.
