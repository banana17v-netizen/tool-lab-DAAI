from __future__ import annotations

import csv
from pathlib import Path

from app.models import FuelMetricRecord


class FuelSnapshotWriter:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    async def append_monthly_csv(self, record: FuelMetricRecord) -> Path:
        target_dir = self.base_dir / f"{record.timestamp:%Y}" / f"{record.timestamp:%m}"
        target_dir.mkdir(parents=True, exist_ok=True)

        file_path = target_dir / f"fuel_metrics_{record.timestamp:%Y%m}.csv"
        file_exists = file_path.exists()

        with file_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            if not file_exists:
                writer.writerow([
                    "timestamp",
                    "brent_price_usd",
                    "exchange_rate",
                    "jet_a1_est_vnd",
                    "han_sgn_fuel_cost",
                ])
            writer.writerow([
                record.timestamp.isoformat(),
                str(record.brent_price_usd),
                str(record.exchange_rate),
                str(record.jet_a1_est_vnd),
                str(record.han_sgn_fuel_cost),
            ])

        return file_path
