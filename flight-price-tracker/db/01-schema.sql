CREATE TABLE IF NOT EXISTS flight_price_ticks (
    timestamp TIMESTAMPTZ NOT NULL,
    flight_number TEXT NOT NULL,
    departure_time TIMESTAMPTZ,
    fare_class TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_flight_price_ticks_time
    ON flight_price_ticks (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_flight_price_ticks_flight
    ON flight_price_ticks (flight_number, departure_time, fare_class, timestamp DESC);

CREATE TABLE IF NOT EXISTS fuel_metrics (
    timestamp TIMESTAMPTZ NOT NULL,
    brent_price_usd NUMERIC(12,4) NOT NULL,
    exchange_rate NUMERIC(12,2) NOT NULL,
    jet_a1_est_vnd NUMERIC(14,2) NOT NULL,
    han_sgn_fuel_cost NUMERIC(18,2) NOT NULL,
    brent_source TEXT NOT NULL DEFAULT 'unknown',
    exchange_rate_source TEXT NOT NULL DEFAULT 'unknown',
    brent_price_timestamp TIMESTAMPTZ,
    exchange_rate_timestamp TIMESTAMPTZ,
    is_fallback BOOLEAN,
    source_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_fuel_metrics_time
    ON fuel_metrics (timestamp DESC);
