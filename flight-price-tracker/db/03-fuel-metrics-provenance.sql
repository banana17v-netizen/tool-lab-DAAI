ALTER TABLE fuel_metrics
    ADD COLUMN IF NOT EXISTS brent_source TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE fuel_metrics
    ADD COLUMN IF NOT EXISTS exchange_rate_source TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE fuel_metrics
    ADD COLUMN IF NOT EXISTS brent_price_timestamp TIMESTAMPTZ;

ALTER TABLE fuel_metrics
    ADD COLUMN IF NOT EXISTS exchange_rate_timestamp TIMESTAMPTZ;

ALTER TABLE fuel_metrics
    ADD COLUMN IF NOT EXISTS is_fallback BOOLEAN;

ALTER TABLE fuel_metrics
    ADD COLUMN IF NOT EXISTS source_note TEXT;