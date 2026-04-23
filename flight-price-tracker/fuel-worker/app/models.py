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


class SourceQuote(BaseModel):
    value: Decimal = Field(gt=0)
    source: str = Field(min_length=1)
    observed_at: datetime | None = None
    is_fallback: bool = False
    note: str | None = None


class FuelMetricRecord(BaseModel):
    timestamp: datetime
    brent_price_usd: Decimal = Field(gt=0)
    exchange_rate: Decimal = Field(gt=0)
    jet_a1_est_vnd: Decimal = Field(gt=0)
    han_sgn_fuel_cost: Decimal = Field(gt=0)
    brent_source: str = Field(min_length=1)
    exchange_rate_source: str = Field(min_length=1)
    brent_price_timestamp: datetime | None = None
    exchange_rate_timestamp: datetime | None = None
    is_fallback: bool = False
    source_note: str | None = None
