from __future__ import annotations

import csv
from pathlib import Path

from app.models import FuelMetricRecord


CSV_COLUMNS = [
    "timestamp",
    "brent_price_usd",
    "exchange_rate",
    "jet_a1_est_vnd",
    "han_sgn_fuel_cost",
    "brent_source",
    "exchange_rate_source",
    "brent_price_timestamp",
    "exchange_rate_timestamp",
    "is_fallback",
    "source_note",
]


class FuelSnapshotWriter:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    async def append_monthly_csv(self, record: FuelMetricRecord) -> Path:
        target_dir = self.base_dir / f"{record.timestamp:%Y}" / f"{record.timestamp:%m}"
        target_dir.mkdir(parents=True, exist_ok=True)

        file_path = target_dir / f"fuel_metrics_{record.timestamp:%Y%m}.csv"
        row = self._serialize_record(record)

        if file_path.exists():
            self._migrate_existing_csv(file_path)

        with file_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            if handle.tell() == 0:
                writer.writeheader()
            writer.writerow(row)

        return file_path

    def _serialize_record(self, record: FuelMetricRecord) -> dict[str, str]:
        return {
            "timestamp": record.timestamp.isoformat(),
            "brent_price_usd": str(record.brent_price_usd),
            "exchange_rate": str(record.exchange_rate),
            "jet_a1_est_vnd": str(record.jet_a1_est_vnd),
            "han_sgn_fuel_cost": str(record.han_sgn_fuel_cost),
            "brent_source": record.brent_source,
            "exchange_rate_source": record.exchange_rate_source,
            "brent_price_timestamp": record.brent_price_timestamp.isoformat() if record.brent_price_timestamp else "",
            "exchange_rate_timestamp": record.exchange_rate_timestamp.isoformat() if record.exchange_rate_timestamp else "",
            "is_fallback": "true" if record.is_fallback else "false",
            "source_note": record.source_note or "",
        }

    def _migrate_existing_csv(self, file_path: Path) -> None:
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames == CSV_COLUMNS:
                return
            existing_rows = list(reader)

        migrated_rows: list[dict[str, str]] = []
        for row in existing_rows:
            migrated_rows.append(
                {
                    "timestamp": row.get("timestamp", ""),
                    "brent_price_usd": row.get("brent_price_usd", ""),
                    "exchange_rate": row.get("exchange_rate", ""),
                    "jet_a1_est_vnd": row.get("jet_a1_est_vnd", ""),
                    "han_sgn_fuel_cost": row.get("han_sgn_fuel_cost", ""),
                    "brent_source": row.get("brent_source", "legacy_unknown"),
                    "exchange_rate_source": row.get("exchange_rate_source", "legacy_unknown"),
                    "brent_price_timestamp": row.get("brent_price_timestamp", ""),
                    "exchange_rate_timestamp": row.get("exchange_rate_timestamp", ""),
                    "is_fallback": row.get("is_fallback", ""),
                    "source_note": row.get("source_note", "migrated from legacy CSV without provenance"),
                }
            )

        with file_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(migrated_rows)
