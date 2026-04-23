from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from app.models import FuelMetricRecord, FuelPricingConfig, SourceQuote


TWO_DECIMALS = Decimal("0.01")
FOUR_DECIMALS = Decimal("0.0001")


class FuelPricingEngine:
    def __init__(self, config: FuelPricingConfig) -> None:
        self.config = config

    def build_metric(self, timestamp: datetime, brent_quote: SourceQuote, exchange_rate_quote: SourceQuote) -> FuelMetricRecord:
        proxy_mops = brent_quote.value * self.config.mops_proxy_multiplier
        jet_a1_est_vnd = (
            (proxy_mops * exchange_rate_quote.value / self.config.barrel_to_liters)
            + self.config.import_tax_vnd_per_liter
            + self.config.environment_tax_vnd_per_liter
            + self.config.premium_vnd_per_liter
        )
        han_sgn_fuel_cost = jet_a1_est_vnd * self.config.han_sgn_estimated_liters

        note_parts = [part for part in [brent_quote.note, exchange_rate_quote.note] if part]

        return FuelMetricRecord(
            timestamp=timestamp,
            brent_price_usd=brent_quote.value.quantize(FOUR_DECIMALS, rounding=ROUND_HALF_UP),
            exchange_rate=exchange_rate_quote.value.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP),
            jet_a1_est_vnd=jet_a1_est_vnd.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP),
            han_sgn_fuel_cost=han_sgn_fuel_cost.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP),
            brent_source=brent_quote.source,
            exchange_rate_source=exchange_rate_quote.source,
            brent_price_timestamp=brent_quote.observed_at,
            exchange_rate_timestamp=exchange_rate_quote.observed_at,
            is_fallback=brent_quote.is_fallback,
            source_note=" | ".join(note_parts) if note_parts else None,
        )
