from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import psycopg
import streamlit as st

st.set_page_config(page_title="VNA Price And Fuel Dashboard", layout="wide")
st.title("Vietnam Airlines Price And Fuel Dashboard")
st.caption("Read-only dashboard fed by the fare scraper and the fuel macro worker.")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dashboard_reader:dashboard_password@db-service:5432/flight_prices")


@st.cache_data(ttl=30)
def load_rows(limit: int) -> pd.DataFrame:
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT timestamp, flight_number, departure_time, fare_class, price
                FROM flight_price_ticks
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()

    frame = pd.DataFrame(
        rows,
        columns=["timestamp", "flight_number", "departure_time", "fare_class", "price"],
    )
    if not frame.empty:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame["departure_time"] = pd.to_datetime(frame["departure_time"], utc=True)
        frame["series"] = frame["flight_number"] + " | " + frame["fare_class"]
    return frame


@st.cache_data(ttl=300)
def load_fuel_rows(limit: int) -> pd.DataFrame:
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT timestamp, brent_price_usd, exchange_rate, jet_a1_est_vnd, han_sgn_fuel_cost
                FROM fuel_metrics
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()

    frame = pd.DataFrame(
        rows,
        columns=["timestamp", "brent_price_usd", "exchange_rate", "jet_a1_est_vnd", "han_sgn_fuel_cost"],
    )
    if not frame.empty:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame


limit = st.sidebar.slider("Rows to load", min_value=100, max_value=5000, value=1000, step=100)
frame = load_rows(limit)
fuel_frame = load_fuel_rows(limit)

if frame.empty and fuel_frame.empty:
    st.warning("No fare or fuel rows found yet. Wait for the workers to write the first cycles.")
    st.stop()

if not frame.empty:
    series_options = sorted(frame["series"].unique().tolist())
    selected_series = st.sidebar.multiselect("Flight / fare class", series_options, default=series_options[: min(5, len(series_options))])

    filtered = frame if not selected_series else frame[frame["series"].isin(selected_series)]
    latest_ts = filtered["timestamp"].max()
    latest_price = filtered.sort_values("timestamp").iloc[-1]["price"]

    st.subheader("Fare Ticks")
    left_col, middle_col, right_col = st.columns(3)
    left_col.metric("Fare rows loaded", f"{len(filtered):,}")
    middle_col.metric("Latest fare scrape", latest_ts.strftime("%Y-%m-%d %H:%M:%S UTC"))
    right_col.metric("Latest fare", f"{latest_price:,.0f}")

    chart = px.line(
        filtered.sort_values("timestamp"),
        x="timestamp",
        y="price",
        color="series",
        markers=True,
        title="Fare movement over time",
    )
    chart.update_layout(height=520, xaxis_title="Collected at", yaxis_title="Price")
    st.plotly_chart(chart, use_container_width=True)

    st.dataframe(
        filtered.sort_values("timestamp", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("Fare worker has not written any rows yet.")

if not fuel_frame.empty:
    latest_fuel = fuel_frame.sort_values("timestamp").iloc[-1]
    st.subheader("Fuel Metrics")
    fuel_col_1, fuel_col_2, fuel_col_3, fuel_col_4 = st.columns(4)
    fuel_col_1.metric("Latest Brent", f"{latest_fuel['brent_price_usd']:,.2f} USD/bbl")
    fuel_col_2.metric("Latest USD/VND", f"{latest_fuel['exchange_rate']:,.0f}")
    fuel_col_3.metric("Jet A1 est.", f"{latest_fuel['jet_a1_est_vnd']:,.0f} VND/L")
    fuel_col_4.metric("HAN-SGN fuel cost", f"{latest_fuel['han_sgn_fuel_cost']:,.0f} VND")

    jet_chart = px.line(
        fuel_frame.sort_values("timestamp"),
        x="timestamp",
        y="jet_a1_est_vnd",
        markers=True,
        title="Estimated Jet A1 cost over time",
    )
    jet_chart.update_layout(height=360, xaxis_title="Collected at", yaxis_title="VND/L")
    st.plotly_chart(jet_chart, use_container_width=True)

    fuel_cost_chart = px.line(
        fuel_frame.sort_values("timestamp"),
        x="timestamp",
        y="han_sgn_fuel_cost",
        markers=True,
        title="Estimated HAN-SGN fuel cost over time",
    )
    fuel_cost_chart.update_layout(height=360, xaxis_title="Collected at", yaxis_title="VND")
    st.plotly_chart(fuel_cost_chart, use_container_width=True)

    st.dataframe(
        fuel_frame.sort_values("timestamp", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("Fuel worker has not written any rows yet.")

if not frame.empty and not fuel_frame.empty:
    fare_daily = (
        frame.assign(day=frame["timestamp"].dt.floor("D"))
        .groupby("day", as_index=False)["price"]
        .mean()
        .rename(columns={"price": "avg_fare"})
    )
    fuel_daily = (
        fuel_frame.assign(day=fuel_frame["timestamp"].dt.floor("D"))
        .groupby("day", as_index=False)["han_sgn_fuel_cost"]
        .mean()
    )
    merged = fare_daily.merge(fuel_daily, on="day", how="inner").sort_values("day")

    if not merged.empty:
        base_fare = merged.iloc[0]["avg_fare"]
        base_fuel = merged.iloc[0]["han_sgn_fuel_cost"]
        if base_fare and base_fuel:
            merged["avg_fare_index"] = merged["avg_fare"] / base_fare * 100
            merged["fuel_cost_index"] = merged["han_sgn_fuel_cost"] / base_fuel * 100
            integrated = merged.melt(
                id_vars=["day"],
                value_vars=["avg_fare_index", "fuel_cost_index"],
                var_name="series",
                value_name="index_value",
            )
            st.subheader("Fuel vs Fare Daily Index")
            integration_chart = px.line(
                integrated,
                x="day",
                y="index_value",
                color="series",
                markers=True,
                title="Normalized daily movement: average fare vs HAN-SGN fuel cost",
            )
            integration_chart.update_layout(height=360, xaxis_title="Day", yaxis_title="Index (base=100)")
            st.plotly_chart(integration_chart, use_container_width=True)
