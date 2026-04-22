from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models import RouteMonitor


@dataclass(slots=True)
class Settings:
    database_url: str
    scrape_interval_seconds: int
    max_concurrency: int
    request_timeout_seconds: int
    retry_attempts: int
    retry_backoff_seconds: int
    vna_api_url: str
    vna_api_method: str
    vna_headers_template: dict[str, Any]
    vna_query_template: dict[str, Any]
    vna_payload_template: dict[str, Any]
    vna_bearer_token: str
    vna_session_header_name: str
    vna_session_id: str
    raw_data_dir: Path
    routes: list[RouteMonitor]


def _as_int(env_name: str, default: int) -> int:
    value = os.getenv(env_name, str(default))
    return int(value)


def _load_json_env(env_name: str, default: str) -> dict[str, Any]:
    value = os.getenv(env_name, default)
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"{env_name} must be a JSON object")
    return parsed


def _load_routes() -> list[RouteMonitor]:
    flights_file = Path(os.getenv("FLIGHTS_FILE", "/app/config/flights.json"))
    with flights_file.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    return [RouteMonitor.model_validate(item) for item in payload]


def load_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "postgresql://tracker:tracker_password@db-service:5432/flight_prices"),
        scrape_interval_seconds=_as_int("SCRAPE_INTERVAL_SECONDS", 60),
        max_concurrency=_as_int("MAX_CONCURRENCY", 12),
        request_timeout_seconds=_as_int("REQUEST_TIMEOUT_SECONDS", 20),
        retry_attempts=_as_int("RETRY_ATTEMPTS", 3),
        retry_backoff_seconds=_as_int("RETRY_BACKOFF_SECONDS", 2),
        vna_api_url=os.getenv("VNA_API_URL", "https://example.com/api/availability"),
        vna_api_method=os.getenv("VNA_API_METHOD", "POST").upper(),
        vna_headers_template=_load_json_env("VNA_HEADERS_TEMPLATE", '{"Accept":"application/json","Content-Type":"application/json"}'),
        vna_query_template=_load_json_env("VNA_QUERY_TEMPLATE", "{}"),
        vna_payload_template=_load_json_env("VNA_PAYLOAD_TEMPLATE", '{"origin":"{origin}","destination":"{destination}","date":"{travel_date}"}'),
        vna_bearer_token=os.getenv("VNA_BEARER_TOKEN", ""),
        vna_session_header_name=os.getenv("VNA_SESSION_HEADER_NAME", "X-Session-Id"),
        vna_session_id=os.getenv("VNA_SESSION_ID", ""),
        raw_data_dir=Path(os.getenv("RAW_DATA_DIR", "/app/raw_data")),
        routes=_load_routes(),
    )
