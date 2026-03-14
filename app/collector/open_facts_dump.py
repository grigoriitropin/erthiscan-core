import csv
import gzip
import io
import os
from collections.abc import Generator
from urllib.request import Request, urlopen

OPEN_FACTS_FOOD_CSV_URL = "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz"
OpenFactsRow = tuple[str, str, str, str | None]
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


def _iter_open_facts_rows() -> Generator[tuple[int, int, int, OpenFactsBatch], None, None]:
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

                if not product_name or not company_name:
                    skipped_rows += 1
                    continue

                batch.append(
                    (
                        barcode,
                        product_name,
                        company_name,
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
            cur.execute("DROP TABLE IF EXISTS open_facts_products_next")
            cur.execute("DROP TABLE IF EXISTS open_facts_products_stage")
            cur.execute(
                "CREATE TABLE open_facts_products_stage ("
                "barcode TEXT NOT NULL, "
                "product_name TEXT NOT NULL, "
                "company_name TEXT NOT NULL, "
                "open_facts_url TEXT"
                ")"
            )
            cur.execute("CREATE TABLE open_facts_products_next (LIKE open_facts_products INCLUDING ALL)")

            with cur.copy(
                "COPY open_facts_products_stage (barcode, product_name, company_name, open_facts_url) FROM STDIN"
            ) as copy:
                for total_rows, kept_rows, skipped_rows, batch in _iter_open_facts_rows():
                    for row in batch:
                        copy.write_row(row)

            cur.execute(
                "INSERT INTO open_facts_products_next (barcode, product_name, company_name, open_facts_url) "
                "SELECT DISTINCT ON (barcode) barcode, product_name, company_name, open_facts_url "
                "FROM open_facts_products_stage "
                "ORDER BY barcode"
            )

            cur.execute("ALTER TABLE open_facts_products RENAME TO open_facts_products_old")
            cur.execute("ALTER TABLE open_facts_products_next RENAME TO open_facts_products")
            cur.execute("DROP TABLE open_facts_products_old")

    print(
        "Open Facts dump import complete: "
        f"total_rows={total_rows} kept_rows={kept_rows} skipped_rows={skipped_rows}"
    )


if __name__ == "__main__":
    import_open_facts_dump()
