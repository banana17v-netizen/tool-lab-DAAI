from __future__ import annotations

import asyncpg

from app.models import FuelMetricRecord


class PostgresStorage:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(dsn=self.dsn, min_size=1, max_size=5)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()

    async def insert_metric(self, record: FuelMetricRecord) -> None:
        if self.pool is None:
            raise RuntimeError("Database pool is not initialized")

        query = """
            INSERT INTO fuel_metrics (
                timestamp,
                brent_price_usd,
                exchange_rate,
                jet_a1_est_vnd,
                han_sgn_fuel_cost,
                brent_source,
                exchange_rate_source,
                brent_price_timestamp,
                exchange_rate_timestamp,
                is_fallback,
                source_note
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """

        async with self.pool.acquire() as conn:
            await conn.execute(
                query,
                record.timestamp,
                record.brent_price_usd,
                record.exchange_rate,
                record.jet_a1_est_vnd,
                record.han_sgn_fuel_cost,
                record.brent_source,
                record.exchange_rate_source,
                record.brent_price_timestamp,
                record.exchange_rate_timestamp,
                record.is_fallback,
                record.source_note,
            )
