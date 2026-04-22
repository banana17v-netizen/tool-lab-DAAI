from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from app.models import FuelMetricRecord, FuelPricingConfig


TWO_DECIMALS = Decimal("0.01")
FOUR_DECIMALS = Decimal("0.0001")


class FuelPricingEngine:
    def __init__(self, config: FuelPricingConfig) -> None:
        self.config = config

    def build_metric(self, timestamp: datetime, brent_price_usd: Decimal, exchange_rate: Decimal) -> FuelMetricRecord:
        proxy_mops = brent_price_usd * self.config.mops_proxy_multiplier
        jet_a1_est_vnd = (
            (proxy_mops * exchange_rate / self.config.barrel_to_liters)
            + self.config.import_tax_vnd_per_liter
            + self.config.environment_tax_vnd_per_liter
            + self.config.premium_vnd_per_liter
        )
        han_sgn_fuel_cost = jet_a1_est_vnd * self.config.han_sgn_estimated_liters

        return FuelMetricRecord(
            timestamp=timestamp,
            brent_price_usd=brent_price_usd.quantize(FOUR_DECIMALS, rounding=ROUND_HALF_UP),
            exchange_rate=exchange_rate.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP),
            jet_a1_est_vnd=jet_a1_est_vnd.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP),
            han_sgn_fuel_cost=han_sgn_fuel_cost.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP),
        )
