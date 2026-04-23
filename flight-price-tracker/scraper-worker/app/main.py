from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from app.config import load_settings
from app.data_lake import DataLakeWriter
from app.scraper import FlightScraper
from app.storage import PostgresStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def _build_travel_dates(base_date: date, offsets: list[int]) -> list[date]:
    return [base_date + timedelta(days=offset) for offset in offsets]


async def run_cycle(scraper: FlightScraper, storage: PostgresStorage, lake_writer: DataLakeWriter) -> None:
    settings = scraper.settings
    semaphore = asyncio.Semaphore(settings.max_concurrency)
    today = datetime.now(timezone.utc).date()

    async def process_route(route, travel_date: date):
        async with semaphore:
            try:
                result = await scraper.fetch(route, travel_date)
                await storage.insert_prices(result.records)
                await lake_writer.write_raw_json(datetime.now(timezone.utc), result.raw_json_line)
                logger.info(
                    "Saved %d ticket rows for %s-%s on %s",
                    len(result.records),
                    route.origin,
                    route.destination,
                    travel_date.isoformat(),
                )
            except Exception as exc:
                logger.exception(
                    "Failed to scrape %s-%s on %s: %s",
                    route.origin,
                    route.destination,
                    travel_date.isoformat(),
                    exc,
                )

    tasks = []
    for route in settings.routes:
        for travel_date in _build_travel_dates(today, route.days_ahead):
            tasks.append(process_route(route, travel_date))

    await asyncio.gather(*tasks)


async def scheduler() -> None:
    settings = load_settings()

    scraper = FlightScraper(settings)

    storage = PostgresStorage(settings.database_url)
    await storage.connect()

    lake_writer = DataLakeWriter(settings.raw_data_dir)

    logger.info("Worker started with %d routes, interval=%ss", len(settings.routes), settings.scrape_interval_seconds)

    if "example.com" in settings.vna_api_url:
        logger.warning(
            "VNA_API_URL is still set to the placeholder endpoint. Update .env with the real API URL before expecting fare data."
        )

    try:
        while True:
            started_at = datetime.now(timezone.utc)
            logger.info("Running scrape cycle at %s", started_at.isoformat())
            try:
                if "example.com" in settings.vna_api_url:
                    logger.warning("Skipping scrape cycle because VNA_API_URL is still the example placeholder.")
                else:
                    await run_cycle(scraper, storage, lake_writer)
            except Exception as exc:
                logger.exception("Cycle-level failure: %s", exc)
            await asyncio.sleep(settings.scrape_interval_seconds)
    finally:
        await storage.close()


if __name__ == "__main__":
    asyncio.run(scheduler())
