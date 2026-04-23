from __future__ import annotations

import asyncio
import csv
import logging
from datetime import date, datetime, time, timezone
from io import StringIO
import xml.etree.ElementTree as ET
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import yfinance as yf

from app.models import SourceQuote


logger = logging.getLogger(__name__)


class BrentPriceClient:
    def __init__(
        self,
        symbol: str,
        timeout_seconds: int,
        fallback_price_usd: Decimal | None = None,
        stooq_symbol: str = "cb.f",
    ) -> None:
        self.symbol = symbol
        self.timeout_seconds = timeout_seconds
        self.fallback_price_usd = fallback_price_usd
        self.stooq_symbol = stooq_symbol

    async def fetch_latest_close(self) -> SourceQuote:
        try:
            return await self._fetch_from_yahoo_chart()
        except Exception as chart_exc:
            try:
                return await self._fetch_from_stooq_csv()
            except Exception as stooq_exc:
                try:
                    return await asyncio.to_thread(self._fetch_sync)
                except Exception as sync_exc:
                    if self.fallback_price_usd is not None:
                        note = f"chart={chart_exc} | stooq={stooq_exc} | yfinance={sync_exc}"
                        logger.warning(
                            "Using configured Brent fallback price %s USD/bbl after live source failures: %s",
                            self.fallback_price_usd,
                            note,
                        )
                        return SourceQuote(
                            value=self.fallback_price_usd,
                            source="configured_fallback",
                            observed_at=None,
                            is_fallback=True,
                            note=note,
                        )
                    raise sync_exc

    async def _fetch_from_yahoo_chart(self) -> SourceQuote:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{self.symbol}"
        params = {"interval": "1d", "range": "5d"}

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = await client.get(url, params=params)
        response.raise_for_status()

        payload = response.json()
        result = payload.get("chart", {}).get("result", [{}])[0]
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        timestamps = result.get("timestamp", [])
        cleaned: list[tuple[datetime | None, Decimal]] = []
        for timestamp_value, close_value in zip(timestamps, closes):
            if close_value is None:
                continue
            observed_at = datetime.fromtimestamp(timestamp_value, tz=timezone.utc)
            cleaned.append((observed_at, Decimal(str(close_value))))
        if not cleaned:
            raise RuntimeError(f"No closing price available for symbol {self.symbol} from Yahoo chart API")
        observed_at, value = cleaned[-1]
        return SourceQuote(
            value=value,
            source="yahoo_chart",
            observed_at=observed_at,
            is_fallback=False,
        )

    async def _fetch_from_stooq_csv(self) -> SourceQuote:
        url = f"https://stooq.com/q/l/?s={self.stooq_symbol}&f=sd2t2ohlcvn&e=csv"

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = await client.get(url)
        response.raise_for_status()

        reader = csv.reader(StringIO(response.text.strip()))
        row = next(reader, None)
        if row is None or len(row) < 4:
            raise RuntimeError(f"No Stooq CSV row returned for symbol {self.stooq_symbol}")

        close_value = row[6].strip() if len(row) > 6 else ""
        date_value = row[1].strip() if len(row) > 1 else ""
        time_value = row[2].strip() if len(row) > 2 else ""
        if not close_value or close_value == "N/D":
            raise RuntimeError(f"No Stooq closing price available for symbol {self.stooq_symbol}")

        return SourceQuote(
            value=Decimal(close_value),
            source="stooq_csv",
            observed_at=self._parse_stooq_timestamp(date_value, time_value),
            is_fallback=False,
            note=f"symbol={self.stooq_symbol}",
        )

    def _fetch_sync(self) -> SourceQuote:
        history = yf.Ticker(self.symbol).history(period="5d", interval="1d", auto_adjust=False, actions=False)
        if history.empty:
            raise RuntimeError(f"No Brent history returned for symbol {self.symbol}")

        closes = history["Close"].dropna()
        if closes.empty:
            raise RuntimeError(f"No closing price available for symbol {self.symbol}")

        observed_at = self._normalize_observed_at(closes.index[-1])
        return SourceQuote(
            value=Decimal(str(closes.iloc[-1])),
            source="yfinance",
            observed_at=observed_at,
            is_fallback=False,
        )

    @staticmethod
    def _normalize_observed_at(value: Any) -> datetime | None:
        if value is None:
            return None
        if hasattr(value, "to_pydatetime"):
            value = value.to_pydatetime()
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
        return None

    @staticmethod
    def _parse_stooq_timestamp(date_value: str, time_value: str) -> datetime | None:
        if not date_value or date_value == "N/D":
            return None
        try:
            parsed_date = datetime.strptime(date_value, "%Y-%m-%d").date()
        except ValueError:
            return None

        parsed_time = time.min
        if time_value and time_value != "N/D":
            try:
                parsed_time = datetime.strptime(time_value, "%H:%M:%S").time()
            except ValueError:
                parsed_time = time.min

        return datetime.combine(parsed_date, parsed_time, tzinfo=timezone.utc)


class VietcombankExchangeClient:
    def __init__(self, url: str, currency_code: str, timeout_seconds: int) -> None:
        self.url = url
        self.currency_code = currency_code.upper()
        self.timeout_seconds = timeout_seconds
        self.local_timezone = ZoneInfo("Asia/Ho_Chi_Minh")

    async def fetch_sell_rate(self) -> SourceQuote:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(self.url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()
        if "json" in content_type:
            rate, observed_at = self._extract_from_json(response.json())
            source = "vietcombank_json"
        else:
            rate, observed_at = self._extract_from_xml(response.text)
            source = "vietcombank_xml"

        if rate is None:
            raise RuntimeError(f"Could not find sell rate for {self.currency_code} in Vietcombank payload")
        return SourceQuote(
            value=rate,
            source=source,
            observed_at=observed_at,
            is_fallback=False,
        )

    def _extract_from_xml(self, payload: str) -> tuple[Decimal | None, datetime | None]:
        root = ET.fromstring(payload)
        sell_keys = ("Sell", "sell", "Ask", "ask", "Selling", "selling")
        observed_at = self._parse_vcb_datetime(root.findtext("DateTime"))

        for element in root.iter():
            currency = (
                element.attrib.get("CurrencyCode")
                or element.attrib.get("currencyCode")
                or element.attrib.get("Currency")
                or element.attrib.get("currency")
                or ""
            ).upper()
            if currency != self.currency_code:
                continue

            for key in sell_keys:
                raw_value = element.attrib.get(key)
                if raw_value:
                    return self._to_decimal(raw_value), observed_at

        return None, observed_at

    def _extract_from_json(self, payload: Any) -> tuple[Decimal | None, datetime | None]:
        sell_keys = {"sell", "selling", "ask", "sellrate", "sell_rate"}
        currency_keys = {"currencycode", "currency", "currency_code", "code"}
        observed_at = self._extract_payload_datetime(payload)

        def walk(node: Any) -> Decimal | None:
            if isinstance(node, dict):
                currency_value = None
                for key, value in node.items():
                    normalized = self._normalize_key(key)
                    if normalized in currency_keys and not isinstance(value, (dict, list)):
                        currency_value = str(value).upper()
                        break

                if currency_value == self.currency_code:
                    for key, value in node.items():
                        normalized = self._normalize_key(key)
                        if normalized in sell_keys and not isinstance(value, (dict, list)):
                            return self._to_decimal(value)

                for value in node.values():
                    nested = walk(value)
                    if nested is not None:
                        return nested
            elif isinstance(node, list):
                for item in node:
                    nested = walk(item)
                    if nested is not None:
                        return nested
            return None

        return walk(payload), observed_at

    def _extract_payload_datetime(self, payload: Any) -> datetime | None:
        datetime_keys = {"datetime", "date_time", "updatedat", "updated_at", "timestamp"}

        def walk(node: Any) -> datetime | None:
            if isinstance(node, dict):
                for key, value in node.items():
                    normalized = self._normalize_key(key)
                    if normalized in datetime_keys and not isinstance(value, (dict, list)):
                        parsed = self._parse_vcb_datetime(value)
                        if parsed is not None:
                            return parsed
                for value in node.values():
                    nested = walk(value)
                    if nested is not None:
                        return nested
            elif isinstance(node, list):
                for item in node:
                    nested = walk(item)
                    if nested is not None:
                        return nested
            return None

        return walk(payload)

    def _parse_vcb_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        for fmt in ("%m/%d/%Y %I:%M:%S %p", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(text, fmt)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=self.local_timezone)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                continue
        return None

    @staticmethod
    def _normalize_key(value: str) -> str:
        return "".join(char for char in value.lower() if char.isalnum())

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        cleaned = str(value).replace(",", "").strip()
        return Decimal(cleaned)
