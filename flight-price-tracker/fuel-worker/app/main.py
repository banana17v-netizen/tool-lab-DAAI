from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import load_settings
from app.economic_data import BrentPriceClient, VietcombankExchangeClient
from app.pricing import FuelPricingEngine
from app.snapshots import FuelSnapshotWriter
from app.storage import PostgresStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def _get_next_run(
    now_local: datetime,
    schedule_mode: str,
    daily_hour: int,
    hourly_interval: int,
    interval_minutes: int,
) -> datetime:
    if schedule_mode == "interval":
        candidate = now_local.replace(second=0, microsecond=0) + timedelta(minutes=interval_minutes)
        if candidate <= now_local:
            candidate += timedelta(minutes=interval_minutes)
        return candidate

    if schedule_mode == "hourly":
        candidate = now_local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=hourly_interval)
        if candidate <= now_local:
            candidate += timedelta(hours=hourly_interval)
        return candidate

    candidate = now_local.replace(hour=daily_hour, minute=0, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return candidate


def _get_retry_run(now_local: datetime, retry_delay_minutes: int) -> datetime:
    return now_local + timedelta(minutes=retry_delay_minutes)


async def run_cycle(
    brent_client: BrentPriceClient,
    exchange_client: VietcombankExchangeClient,
    pricing_engine: FuelPricingEngine,
    storage: PostgresStorage,
    snapshot_writer: FuelSnapshotWriter,
) -> bool:
    try:
        timestamp = datetime.now(timezone.utc)
        brent_quote = await brent_client.fetch_latest_close()
        exchange_rate_quote = await exchange_client.fetch_sell_rate()
        record = pricing_engine.build_metric(timestamp, brent_quote, exchange_rate_quote)

        await storage.insert_metric(record)
        csv_path = await snapshot_writer.append_monthly_csv(record)

        logger.info(
            "Saved fuel metric | Brent=%s USD/bbl (%s) | FX=%s VND/USD (%s) | fallback=%s | JetA1=%s VND/L | HAN-SGN=%s VND | CSV=%s",
            record.brent_price_usd,
            record.brent_source,
            record.exchange_rate,
            record.exchange_rate_source,
            record.is_fallback,
            record.jet_a1_est_vnd,
            record.han_sgn_fuel_cost,
            csv_path,
        )
        return True
    except Exception as exc:
        logger.exception("Fuel worker cycle failed: %s", exc)
        return False


async def scheduler() -> None:
    settings = load_settings()
    timezone_local = ZoneInfo(settings.fuel_timezone_name)

    brent_client = BrentPriceClient(
        settings.pricing.brent_symbol,
        settings.request_timeout_seconds,
        settings.fuel_brent_fallback_usd,
        settings.stooq_brent_symbol,
    )
    exchange_client = VietcombankExchangeClient(
        settings.vcb_exchange_url,
        settings.vcb_currency_code,
        settings.request_timeout_seconds,
    )
    pricing_engine = FuelPricingEngine(settings.pricing)
    storage = PostgresStorage(settings.database_url)
    snapshot_writer = FuelSnapshotWriter(settings.fuel_data_dir)

    await storage.connect()
    logger.info(
        "Fuel worker started | mode=%s | daily_hour=%s | hourly_interval=%s | interval_minutes=%s | timezone=%s",
        settings.fuel_schedule_mode,
        settings.fuel_daily_hour,
        settings.fuel_hourly_interval,
        settings.fuel_interval_minutes,
        settings.fuel_timezone_name,
    )

    try:
        last_cycle_succeeded = True
        if settings.fuel_run_on_startup:
            last_cycle_succeeded = await run_cycle(brent_client, exchange_client, pricing_engine, storage, snapshot_writer)

        while True:
            now_local = datetime.now(timezone_local)
            if last_cycle_succeeded:
                next_run = _get_next_run(
                    now_local,
                    settings.fuel_schedule_mode,
                    settings.fuel_daily_hour,
                    settings.fuel_hourly_interval,
                    settings.fuel_interval_minutes,
                )
            else:
                next_run = _get_retry_run(now_local, settings.fuel_retry_delay_minutes)
            sleep_seconds = max(1.0, (next_run - now_local).total_seconds())
            logger.info("Next fuel update scheduled at %s", next_run.isoformat())
            await asyncio.sleep(sleep_seconds)
            last_cycle_succeeded = await run_cycle(
                brent_client,
                exchange_client,
                pricing_engine,
                storage,
                snapshot_writer,
            )
    finally:
        await storage.close()


if __name__ == "__main__":
    asyncio.run(scheduler())
