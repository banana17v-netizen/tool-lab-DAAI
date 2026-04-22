from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class RouteMonitor(BaseModel):
    origin: str
    destination: str
    days_ahead: list[int] = Field(min_length=1)


class TicketPriceRecord(BaseModel):
    timestamp: datetime
    flight_number: str
    departure_time: datetime | None = None
    fare_class: str
    price: Decimal = Field(gt=0)


class ScrapeSnapshot(BaseModel):
    collected_at: datetime
    origin: str
    destination: str
    travel_date: date
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]


@dataclass(slots=True)
class FetchResult:
    records: list[TicketPriceRecord]
    raw_json_line: str
