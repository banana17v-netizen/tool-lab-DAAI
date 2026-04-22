from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class FuelPricingConfig(BaseModel):
    brent_symbol: str = "BZ=F"
    mops_proxy_multiplier: Decimal = Decimal("1.0")
    barrel_to_liters: Decimal = Decimal("158.987")
    import_tax_vnd_per_liter: Decimal = Decimal("0")
    environment_tax_vnd_per_liter: Decimal = Decimal("1000")
    premium_vnd_per_liter: Decimal = Decimal("1800")
    han_sgn_estimated_liters: Decimal = Decimal("9800")


class FuelMetricRecord(BaseModel):
    timestamp: datetime
    brent_price_usd: Decimal = Field(gt=0)
    exchange_rate: Decimal = Field(gt=0)
    jet_a1_est_vnd: Decimal = Field(gt=0)
    han_sgn_fuel_cost: Decimal = Field(gt=0)
