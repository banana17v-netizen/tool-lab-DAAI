from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from app.models import FuelPricingConfig


@dataclass(slots=True)
class Settings:
    database_url: str
    request_timeout_seconds: int
    fuel_data_dir: Path
    fuel_config_file: Path
    fuel_schedule_mode: str
    fuel_daily_hour: int
    fuel_hourly_interval: int
    fuel_timezone_name: str
    fuel_run_on_startup: bool
    vcb_exchange_url: str
    vcb_currency_code: str
    pricing: FuelPricingConfig


def _as_int(env_name: str, default: int) -> int:
    return int(os.getenv(env_name, str(default)))


def _as_bool(env_name: str, default: bool) -> bool:
    raw = os.getenv(env_name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    config_path = Path(os.getenv("FUEL_CONFIG_FILE", "/app/config/pricing.json"))
    with config_path.open("r", encoding="utf-8") as handle:
        pricing = FuelPricingConfig.model_validate(json.load(handle))

    schedule_mode = os.getenv("FUEL_SCHEDULE_MODE", "daily").strip().lower()
    if schedule_mode not in {"daily", "hourly"}:
        raise ValueError("FUEL_SCHEDULE_MODE must be `daily` or `hourly`")

    fuel_hourly_interval = _as_int("FUEL_HOURLY_INTERVAL", 1)
    if fuel_hourly_interval <= 0:
        raise ValueError("FUEL_HOURLY_INTERVAL must be greater than zero")

    fuel_daily_hour = _as_int("FUEL_DAILY_HOUR", 8)
    if fuel_daily_hour < 0 or fuel_daily_hour > 23:
        raise ValueError("FUEL_DAILY_HOUR must be between 0 and 23")

    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql://tracker:tracker_password@db-service:5432/flight_prices"),
        request_timeout_seconds=_as_int("FUEL_REQUEST_TIMEOUT_SECONDS", 20),
        fuel_data_dir=Path(os.getenv("FUEL_DATA_DIR", "/app/fuel_data")),
        fuel_config_file=config_path,
        fuel_schedule_mode=schedule_mode,
        fuel_daily_hour=fuel_daily_hour,
        fuel_hourly_interval=fuel_hourly_interval,
        fuel_timezone_name=os.getenv("FUEL_TIMEZONE", "Asia/Ho_Chi_Minh"),
        fuel_run_on_startup=_as_bool("FUEL_RUN_ON_STARTUP", True),
        vcb_exchange_url=os.getenv(
            "VCB_EXCHANGE_URL",
            "https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx?b=10",
        ),
        vcb_currency_code=os.getenv("VCB_CURRENCY_CODE", "USD"),
        pricing=pricing,
    )
