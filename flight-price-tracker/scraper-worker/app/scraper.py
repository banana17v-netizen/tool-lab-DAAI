from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from app.config import Settings
from app.models import FetchResult, RouteMonitor, ScrapeSnapshot, TicketPriceRecord


class FlightScraper:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def fetch(self, route: RouteMonitor, travel_date: date) -> FetchResult:
        last_exc: Exception | None = None

        for _ in range(self.settings.retry_attempts):
            collected_at = datetime.now(timezone.utc)
            context = self._build_context(route, travel_date)
            headers = self._build_headers(context)
            params = self._render_template(self.settings.vna_query_template, context)
            payload = self._render_template(self.settings.vna_payload_template, context)

            try:
                async with httpx.AsyncClient(
                    timeout=self.settings.request_timeout_seconds,
                    http2=True,
                ) as client:
                    response = await client.request(
                        self.settings.vna_api_method,
                        self.settings.vna_api_url,
                        headers=headers,
                        params=params,
                        json=payload if self.settings.vna_api_method != "GET" else None,
                    )

                response.raise_for_status()

                response_payload = self._extract_payload(response)
                records = self._extract_ticket_records(response_payload, collected_at)
                snapshot = ScrapeSnapshot(
                    collected_at=collected_at,
                    origin=route.origin,
                    destination=route.destination,
                    travel_date=travel_date,
                    request_payload={
                        "method": self.settings.vna_api_method,
                        "url": self.settings.vna_api_url,
                        "headers": headers,
                        "params": params,
                        "json": payload,
                    },
                    response_payload=response_payload,
                )
                return FetchResult(
                    records=records,
                    raw_json_line=json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False),
                )
            except Exception as exc:
                last_exc = exc

        if last_exc is None:
            raise RuntimeError("Failed to fetch flight price after retries")
        raise last_exc

    def _build_context(self, route: RouteMonitor, travel_date: date) -> dict[str, str]:
        return {
            "origin": route.origin,
            "destination": route.destination,
            "travel_date": travel_date.isoformat(),
            "bearer_token": self.settings.vna_bearer_token,
            "session_id": self.settings.vna_session_id,
        }

    def _build_headers(self, context: dict[str, str]) -> dict[str, str]:
        headers = self._render_template(self.settings.vna_headers_template, context)
        if self.settings.vna_bearer_token:
            headers["Authorization"] = f"Bearer {self.settings.vna_bearer_token}"
        if self.settings.vna_session_header_name and self.settings.vna_session_id:
            headers[self.settings.vna_session_header_name] = self.settings.vna_session_id
        return {key: value for key, value in headers.items() if value not in {None, ""}}

    @staticmethod
    def _extract_payload(response: httpx.Response) -> dict[str, Any]:
        raw = response.json()
        return raw if isinstance(raw, dict) else {"results": raw}

    def _extract_ticket_records(self, payload: dict[str, Any], collected_at: datetime) -> list[TicketPriceRecord]:
        records: list[TicketPriceRecord] = []
        seen: set[tuple[str, str, str, str]] = set()

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                record = self._build_record(node, collected_at)
                if record is not None:
                    dedupe_key = (
                        record.flight_number,
                        record.departure_time.isoformat() if record.departure_time else "",
                        record.fare_class,
                        str(record.price),
                    )
                    if dedupe_key not in seen:
                        seen.add(dedupe_key)
                        records.append(record)

                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(payload)
        if not records:
            raise ValueError("Could not extract any ticket rows from the VNA response payload")
        return records

    def _build_record(self, node: dict[str, Any], collected_at: datetime) -> TicketPriceRecord | None:
        flight_number = self._find_first_value(node, {"flightnumber", "flight_number", "flightno", "flight_no", "flightcode"})
        price_value = self._find_price_value(node)

        if flight_number is None or price_value is None:
            return None

        departure_raw = self._find_first_value(node, {"departuretime", "departure_time", "departuredatetime", "departure_date_time", "departureat"})
        fare_class = self._find_first_value(node, {"fareclass", "fare_class", "farefamily", "brandname", "bundle", "faretype", "classname"}) or "UNKNOWN"

        return TicketPriceRecord(
            timestamp=collected_at,
            flight_number=str(flight_number),
            departure_time=self._parse_datetime(departure_raw),
            fare_class=str(fare_class),
            price=self._to_decimal(price_value),
        )

    def _find_first_value(self, node: Any, accepted_keys: set[str]) -> Any | None:
        if isinstance(node, dict):
            for key, value in node.items():
                normalized_key = self._normalize_key(key)
                if normalized_key in accepted_keys and not isinstance(value, (dict, list)):
                    return value
                nested = self._find_first_value(value, accepted_keys)
                if nested is not None:
                    return nested
        elif isinstance(node, list):
            for item in node:
                nested = self._find_first_value(item, accepted_keys)
                if nested is not None:
                    return nested
        return None

    def _find_price_value(self, node: Any) -> Any | None:
        if isinstance(node, dict):
            for key, value in node.items():
                normalized_key = self._normalize_key(key)
                if normalized_key in {"price", "amount", "totalamount", "fareamount", "totalprice", "total_price", "value"}:
                    if isinstance(value, dict):
                        nested = self._find_price_value(value)
                        if nested is not None:
                            return nested
                    elif not isinstance(value, list):
                        return value
                nested = self._find_price_value(value)
                if nested is not None:
                    return nested
        elif isinstance(node, list):
            for item in node:
                nested = self._find_price_value(item)
                if nested is not None:
                    return nested
        return None

    def _render_template(self, value: Any, context: dict[str, str]) -> Any:
        if isinstance(value, dict):
            return {key: self._render_template(item, context) for key, item in value.items()}
        if isinstance(value, list):
            return [self._render_template(item, context) for item in value]
        if isinstance(value, str):
            return value.format(**context)
        return value

    @staticmethod
    def _normalize_key(value: str) -> str:
        return "".join(char for char in value.lower() if char.isalnum())

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value in {None, ""}:
            return None
        text = str(value).strip()
        if text.endswith("Z"):
            text = text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value))

        cleaned = str(value).replace(",", "").replace("$", "").strip()
        return Decimal(cleaned)
