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
                    verify=self.settings.vna_verify_ssl,
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
                records = self._extract_ticket_records(response_payload, route, collected_at)
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
            "trip_duration": str(route.trip_duration),
            "range_of_departure": str(route.range_of_departure),
            "location": route.location,
            "bearer_token": self.settings.vna_bearer_token,
            "session_id": self.settings.vna_session_id,
        }

    def _build_headers(self, context: dict[str, str]) -> dict[str, str]:
        headers = self._render_template(self.settings.vna_headers_template, context)
        if self.settings.vna_bearer_token:
            headers["Authorization"] = f"Bearer {self.settings.vna_bearer_token}"
        if self.settings.vna_session_header_name and self.settings.vna_session_id:
            headers[self.settings.vna_session_header_name] = self.settings.vna_session_id
        if self.settings.vna_cookie:
            headers["Cookie"] = self.settings.vna_cookie
        return {key: value for key, value in headers.items() if value not in {None, ""}}

    @staticmethod
    def _extract_payload(response: httpx.Response) -> dict[str, Any]:
        raw = response.json()
        return raw if isinstance(raw, dict) else {"results": raw}

    def _extract_ticket_records(
        self,
        payload: dict[str, Any],
        route: RouteMonitor,
        collected_at: datetime,
    ) -> list[TicketPriceRecord]:
        parser_mode = self.settings.vna_parser_mode

        if parser_mode in {"best_price_calendar", "auto"}:
            grid_records = self._extract_best_price_grid_records(payload, route, collected_at)
            if grid_records and parser_mode != "auto":
                return grid_records
            if grid_records and parser_mode == "auto":
                return grid_records

        if parser_mode in {"fare_options", "auto"}:
            fare_option_records = self._extract_fare_option_records(payload, collected_at)
            if fare_option_records:
                return fare_option_records

        if parser_mode in {"skyscanner_itineraries", "auto"}:
            skyscanner_records = self._extract_skyscanner_itinerary_records(payload, collected_at)
            if skyscanner_records:
                return skyscanner_records

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

    def _extract_skyscanner_itinerary_records(
        self,
        payload: dict[str, Any],
        collected_at: datetime,
    ) -> list[TicketPriceRecord]:
        results = payload.get("itineraries", {}).get("results")
        if not isinstance(results, list):
            return []

        records: list[TicketPriceRecord] = []
        seen: set[tuple[str, str, str, str]] = set()
        for itinerary in results:
            if not isinstance(itinerary, dict):
                continue

            price_raw = itinerary.get("price", {}).get("raw")
            legs = itinerary.get("legs")
            if price_raw in {None, ""} or not isinstance(legs, list) or not legs:
                continue

            departure_time = self._parse_datetime(legs[0].get("departure"))
            flight_number = self._build_skyscanner_flight_number(legs)
            fare_class = self._build_skyscanner_fare_class(itinerary)
            record = TicketPriceRecord(
                timestamp=collected_at,
                flight_number=flight_number,
                departure_time=departure_time,
                fare_class=fare_class,
                price=self._to_decimal(price_raw),
            )
            dedupe_key = (
                record.flight_number,
                record.departure_time.isoformat() if record.departure_time else "",
                record.fare_class,
                str(record.price),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            records.append(record)

        return records

    def _build_skyscanner_flight_number(self, legs: list[Any]) -> str:
        leg_codes: list[str] = []
        for leg in legs:
            if not isinstance(leg, dict):
                continue
            segment_codes: list[str] = []
            segments = leg.get("segments")
            if isinstance(segments, list):
                for segment in segments:
                    if not isinstance(segment, dict):
                        continue
                    carrier_code = ""
                    marketing_carrier = segment.get("marketingCarrier")
                    if isinstance(marketing_carrier, dict):
                        carrier_code = str(marketing_carrier.get("alternateId") or "")
                    flight_number = str(segment.get("flightNumber") or "")
                    combined = f"{carrier_code}{flight_number}".strip()
                    if combined:
                        segment_codes.append(combined)

            if not segment_codes:
                leg_id = str(leg.get("id") or "")
                if leg_id:
                    segment_codes.append(leg_id)
            if segment_codes:
                leg_codes.append("+".join(segment_codes))

        return " | ".join(leg_codes) or "SKYSCANNER_ITINERARY"

    def _build_skyscanner_fare_class(self, itinerary: dict[str, Any]) -> str:
        pricing_options = itinerary.get("pricingOptions")
        if isinstance(pricing_options, list) and pricing_options:
            first_option = pricing_options[0]
            if isinstance(first_option, dict):
                items = first_option.get("items")
                if isinstance(items, list) and items:
                    first_item = items[0]
                    if isinstance(first_item, dict):
                        booking_proposition = first_item.get("bookingProposition")
                        if booking_proposition:
                            return str(booking_proposition)

        total_stops = 0
        legs = itinerary.get("legs")
        if isinstance(legs, list):
            for leg in legs:
                if isinstance(leg, dict):
                    total_stops += int(leg.get("stopCount") or 0)
        return f"SKYSCANNER_{total_stops}_STOP"

    def _extract_fare_option_records(
        self,
        payload: dict[str, Any],
        collected_at: datetime,
    ) -> list[TicketPriceRecord]:
        records: list[TicketPriceRecord] = []
        seen: set[tuple[str, str, str, str]] = set()

        def walk(node: Any, current_flight: dict[str, Any] | None = None) -> None:
            if isinstance(node, dict):
                flight_context = current_flight
                if self._looks_like_flight_node(node):
                    flight_context = node

                if flight_context is not None:
                    records.extend(self._build_fare_records_from_node(flight_context, node, collected_at, seen))

                for value in node.values():
                    walk(value, flight_context)
            elif isinstance(node, list):
                for item in node:
                    walk(item, current_flight)

        walk(payload)
        return records

    def _build_fare_records_from_node(
        self,
        flight_node: dict[str, Any],
        node: dict[str, Any],
        collected_at: datetime,
        seen: set[tuple[str, str, str, str]],
    ) -> list[TicketPriceRecord]:
        if not self._looks_like_fare_option_node(node):
            return []

        flight_number = self._find_first_value(
            flight_node,
            {"flightnumber", "flight_number", "flightno", "flight_no", "flightcode", "marketingflightnumber"},
        )
        if flight_number is None:
            return []

        departure_raw = self._find_first_value(
            flight_node,
            {"departuretime", "departure_time", "departuredatetime", "departure_date_time", "departureat", "scheduleddeparturedatetime"},
        )
        departure_time = self._parse_datetime(departure_raw)

        fare_class = self._find_first_value(
            node,
            {
                "fareclass",
                "fare_class",
                "farefamily",
                "brandname",
                "bundle",
                "faretype",
                "classname",
                "brandcode",
                "cabinclass",
                "cabinclassname",
                "bookingclass",
            },
        ) or "UNKNOWN"
        price_value = self._find_price_value(node)
        if price_value is None:
            return []

        record = TicketPriceRecord(
            timestamp=collected_at,
            flight_number=str(flight_number),
            departure_time=departure_time,
            fare_class=str(fare_class),
            price=self._to_decimal(price_value),
        )
        dedupe_key = (
            record.flight_number,
            record.departure_time.isoformat() if record.departure_time else "",
            record.fare_class,
            str(record.price),
        )
        if dedupe_key in seen:
            return []
        seen.add(dedupe_key)
        return [record]

    def _looks_like_flight_node(self, node: dict[str, Any]) -> bool:
        return self._find_first_value(
            node,
            {"flightnumber", "flight_number", "flightno", "flight_no", "flightcode", "marketingflightnumber"},
        ) is not None

    def _looks_like_fare_option_node(self, node: dict[str, Any]) -> bool:
        has_fare_label = self._find_first_value(
            node,
            {
                "fareclass",
                "fare_class",
                "farefamily",
                "brandname",
                "bundle",
                "faretype",
                "classname",
                "brandcode",
                "cabinclass",
                "cabinclassname",
                "bookingclass",
            },
        ) is not None
        return has_fare_label and self._find_price_value(node) is not None

    def _extract_best_price_grid_records(
        self,
        payload: dict[str, Any],
        route: RouteMonitor,
        collected_at: datetime,
    ) -> list[TicketPriceRecord]:
        prices = payload.get("data", {}).get("prices")
        if not isinstance(prices, list):
            return []

        records: list[TicketPriceRecord] = []
        for item in prices:
            if not isinstance(item, dict):
                continue

            departure_date = item.get("departureDate")
            return_date = item.get("returnDate")
            price_entries = item.get("price")
            if not departure_date or not isinstance(price_entries, list) or not price_entries:
                continue

            total_entry = next((entry for entry in price_entries if isinstance(entry, dict) and entry.get("total")), None)
            if total_entry is None:
                continue

            departure_time = self._parse_datetime(departure_date)
            total_price = total_entry.get("total")
            currency = total_entry.get("currencyCode") or "VND"
            return_suffix = f"_{return_date}" if return_date else ""

            records.append(
                TicketPriceRecord(
                    timestamp=collected_at,
                    flight_number=f"{route.origin}-{route.destination}",
                    departure_time=departure_time,
                    fare_class=f"BEST_PRICE_RT_{route.trip_duration}D_{currency}{return_suffix}",
                    price=self._to_decimal(total_price),
                )
            )

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
            rendered = value.format(**context)
            if value.startswith("{") and value.endswith("}") and value.count("{") == 1 and value.count("}") == 1:
                try:
                    return json.loads(rendered)
                except json.JSONDecodeError:
                    return rendered
            return rendered
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
