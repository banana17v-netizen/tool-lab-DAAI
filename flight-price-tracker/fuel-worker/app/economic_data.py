from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from decimal import Decimal
from typing import Any

import httpx
import yfinance as yf


class BrentPriceClient:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    async def fetch_latest_close(self) -> Decimal:
        return await asyncio.to_thread(self._fetch_sync)

    def _fetch_sync(self) -> Decimal:
        history = yf.Ticker(self.symbol).history(period="5d", interval="1d", auto_adjust=False, actions=False)
        if history.empty:
            raise RuntimeError(f"No Brent history returned for symbol {self.symbol}")

        closes = history["Close"].dropna()
        if closes.empty:
            raise RuntimeError(f"No closing price available for symbol {self.symbol}")

        return Decimal(str(closes.iloc[-1]))


class VietcombankExchangeClient:
    def __init__(self, url: str, currency_code: str, timeout_seconds: int) -> None:
        self.url = url
        self.currency_code = currency_code.upper()
        self.timeout_seconds = timeout_seconds

    async def fetch_sell_rate(self) -> Decimal:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(self.url)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()
        if "json" in content_type:
            rate = self._extract_from_json(response.json())
        else:
            rate = self._extract_from_xml(response.text)

        if rate is None:
            raise RuntimeError(f"Could not find sell rate for {self.currency_code} in Vietcombank payload")
        return rate

    def _extract_from_xml(self, payload: str) -> Decimal | None:
        root = ET.fromstring(payload)
        sell_keys = ("Sell", "sell", "Ask", "ask", "Selling", "selling")

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
                    return self._to_decimal(raw_value)

        return None

    def _extract_from_json(self, payload: Any) -> Decimal | None:
        sell_keys = {"sell", "selling", "ask", "sellrate", "sell_rate"}
        currency_keys = {"currencycode", "currency", "currency_code", "code"}

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

        return walk(payload)

    @staticmethod
    def _normalize_key(value: str) -> str:
        return "".join(char for char in value.lower() if char.isalnum())

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        cleaned = str(value).replace(",", "").strip()
        return Decimal(cleaned)
