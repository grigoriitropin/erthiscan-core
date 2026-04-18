import csv
import gzip
import io
import os
import sys
from collections.abc import Generator
from urllib.request import Request, urlopen

from app.collector.open_facts import normalize_company_name, normalize_product_name
from app.collector.utils import python_normalize_name

OPEN_FACTS_FOOD_CSV_URL = "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz"
OpenFactsRow = tuple[str, str, str, str, str | None]
OpenFactsBatch = list[OpenFactsRow]


def _get_sync_db_url() -> str:
    db_url = os.getenv("DB_WRITE_URL")
    if not db_url:
        raise RuntimeError("DB_WRITE_URL is not set")

    if db_url.startswith("postgresql+asyncpg://"):
        return db_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    if db_url.startswith("postgresql+psycopg://"):
        return db_url.replace("postgresql+psycopg://", "postgresql://", 1)

    return db_url


def _pick_first_value(*values: str | None) -> str | None:
    for value in values:
        if value is None:
            continue

        stripped = value.strip()
        if stripped:
            return stripped

    return None


def _extract_company_name(row: dict[str, str | None]) -> str | None:
    brand_owner = row.get("brand_owner")
    if brand_owner:
        stripped = brand_owner.strip()
        if stripped:
            return stripped

    brands = row.get("brands")
    if not brands:
        return None

    first_brand = brands.split(",", maxsplit=1)[0].strip()
    return first_brand or None


def _set_csv_field_limit() -> None:
    limit = sys.maxsize

    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def _iter_open_facts_rows() -> Generator[tuple[int, int, int, OpenFactsBatch], None, None]:
    _set_csv_field_limit()

    request = Request(
        OPEN_FACTS_FOOD_CSV_URL,
        headers={
            "User-Agent": "ErthiscanCore/0.1",
            "Accept": "application/gzip",
        },
    )

    total_rows = 0
    kept_rows = 0
    skipped_rows = 0
    batch: OpenFactsBatch = []

    with urlopen(request, timeout=300) as response:
        with gzip.GzipFile(fileobj=response) as compressed_stream:
            text_stream = io.TextIOWrapper(compressed_stream, encoding="utf-8", newline="")
            reader = csv.DictReader(text_stream, delimiter="\t")

            for row in reader:
                total_rows += 1

                barcode = (row.get("code") or "").strip()
                if len(barcode) != 13 or not barcode.isdigit():
                    skipped_rows += 1
                    continue

                product_name = _pick_first_value(
                    row.get("product_name_en"),
                    row.get("product_name"),
                    row.get("generic_name_en"),
                    row.get("generic_name"),
                )
                company_name = _extract_company_name(row)

                normalized_company_name = normalize_company_name(company_name, barcode)
                batch.append(
                    (
                        barcode,
                        normalize_product_name(product_name),
                        normalized_company_name,
                        python_normalize_name(normalized_company_name),
                        f"https://world.openfoodfacts.org/product/{barcode}",
                    )
                )
                kept_rows += 1

                if len(batch) >= 5000:
                    yield total_rows, kept_rows, skipped_rows, batch
                    batch = []

    if batch:
        yield total_rows, kept_rows, skipped_rows, batch


def import_open_facts_dump() -> None:
    import psycopg

    db_url = _get_sync_db_url()
    total_rows = 0
    kept_rows = 0
    skipped_rows = 0

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Create temporary staging table
            cur.execute("""
                CREATE TEMP TABLE import_stage (
                    barcode TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    company_name_normalized TEXT NOT NULL,
                    open_facts_url TEXT
                ) ON COMMIT DROP
            """)

            # Stream CSV rows directly into staging table
            with cur.copy(
                "COPY import_stage (barcode, product_name, company_name, company_name_normalized, open_facts_url) FROM STDIN"
            ) as copy:
                for total_rows, kept_rows, skipped_rows, batch in _iter_open_facts_rows():
                    for row in batch:
                        copy.write_row(row)

            # Upsert companies (only insert new ones, update name_normalized if changed)
            cur.execute("""
                INSERT INTO companies (name, name_normalized, ethical_score, top_level_report_count, pending_vote_count)
                SELECT DISTINCT
                    company_name,
                    company_name_normalized,
                    0.0,
                    0,
                    0
                FROM import_stage
                ON CONFLICT (name) DO UPDATE SET
                    name_normalized = EXCLUDED.name_normalized
                WHERE companies.name_normalized IS DISTINCT FROM EXCLUDED.name_normalized
            """)

            # Upsert products (join with companies to get company_id)
            cur.execute("""
                INSERT INTO products (barcode, name, company_id, open_facts_url)
                SELECT
                    stage.barcode,
                    stage.product_name,
                    companies.id,
                    stage.open_facts_url
                FROM import_stage stage
                JOIN companies ON companies.name = stage.company_name
                ON CONFLICT (barcode) DO UPDATE SET
                    name = EXCLUDED.name,
                    company_id = EXCLUDED.company_id,
                    open_facts_url = EXCLUDED.open_facts_url
                WHERE products.name IS DISTINCT FROM EXCLUDED.name
                   OR products.company_id IS DISTINCT FROM EXCLUDED.company_id
                   OR products.open_facts_url IS DISTINCT FROM EXCLUDED.open_facts_url
            """)

    # VACUUM cannot run inside a transaction block.
    # psycopg defaults to autocommit=False, so we must connect with autocommit=True.
    with psycopg.connect(db_url, autocommit=True) as conn_vac:
        conn_vac.execute("VACUUM (ANALYZE) products")
        conn_vac.execute("VACUUM (ANALYZE) companies")
        # CHECKPOINT after mass updates to help PostgreSQL manage WAL
        conn_vac.execute("CHECKPOINT")

    print(
        "Open Facts dump import complete: "
        f"total_rows={total_rows} kept_rows={kept_rows} skipped_rows={skipped_rows}"
    )


if __name__ == "__main__":
    import_open_facts_dump()