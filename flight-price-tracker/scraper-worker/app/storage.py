from __future__ import annotations

import asyncpg

from app.models import TicketPriceRecord


class PostgresStorage:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(dsn=self.dsn, min_size=1, max_size=10)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()

    async def insert_prices(self, records: list[TicketPriceRecord]) -> None:
        if self.pool is None:
            raise RuntimeError("Database pool is not initialized")

        if not records:
            return

        query = """
            INSERT INTO flight_price_ticks (
                timestamp,
                flight_number,
                departure_time,
                fare_class,
                price
            ) VALUES ($1, $2, $3, $4, $5)
        """

        async with self.pool.acquire() as conn:
            await conn.executemany(
                query,
                [
                    (
                        record.timestamp,
                        record.flight_number,
                        record.departure_time,
                        record.fare_class,
                        record.price,
                    )
                    for record in records
                ],
            )
