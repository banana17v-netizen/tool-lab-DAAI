from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import psycopg
import streamlit as st

st.set_page_config(page_title="VNA Price And Fuel Dashboard", layout="wide")
st.title("Vietnam Airlines Price And Fuel Dashboard")
st.caption("Read-only dashboard fed by the fare scraper and the fuel macro worker.")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://dashboard_reader:dashboard_password@db-service:5432/flight_prices")
VNA_API_URL = os.getenv("VNA_API_URL", "")
DASHBOARD_REFRESH_SECONDS = int(os.getenv("DASHBOARD_REFRESH_SECONDS", "15"))


@st.cache_data(ttl=DASHBOARD_REFRESH_SECONDS)
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


@st.cache_data(ttl=DASHBOARD_REFRESH_SECONDS)
def load_fuel_rows(limit: int) -> pd.DataFrame:
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT timestamp, brent_price_usd, exchange_rate, jet_a1_est_vnd, han_sgn_fuel_cost,
                       brent_source, exchange_rate_source, brent_price_timestamp, exchange_rate_timestamp,
                       is_fallback, source_note
                FROM fuel_metrics
                ORDER BY timestamp DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()

    frame = pd.DataFrame(
        rows,
        columns=[
            "timestamp",
            "brent_price_usd",
            "exchange_rate",
            "jet_a1_est_vnd",
            "han_sgn_fuel_cost",
            "brent_source",
            "exchange_rate_source",
            "brent_price_timestamp",
            "exchange_rate_timestamp",
            "is_fallback",
            "source_note",
        ],
    )
    if not frame.empty:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame["brent_price_timestamp"] = pd.to_datetime(frame["brent_price_timestamp"], utc=True)
        frame["exchange_rate_timestamp"] = pd.to_datetime(frame["exchange_rate_timestamp"], utc=True)
        frame["source_mode"] = frame["is_fallback"].apply(
            lambda value: "Fallback" if value is True else ("Live" if value is False else "Unknown")
        )
    return frame


limit = st.sidebar.slider("Rows to load", min_value=100, max_value=5000, value=1000, step=100)
st.sidebar.caption(f"Dashboard refresh cache: {DASHBOARD_REFRESH_SECONDS}s")
if st.sidebar.button("Refresh now", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

frame = load_rows(limit)
fuel_frame = load_fuel_rows(limit)

if frame.empty and fuel_frame.empty:
    st.warning("No fare or fuel rows found yet.")
    if "example.com" in VNA_API_URL:
        st.info("Fare data is empty because the scraper is still configured with the example VNA endpoint in .env. Replace it with the real API request details to collect ticket prices.")
    st.info("Fuel data is empty because the fuel worker has not saved a successful cycle yet. If this is a fresh run, check the worker logs for external source errors or rate limits.")
    st.stop()

if not frame.empty:
    series_options = sorted(frame["series"].unique().tolist())
    selected_series = st.sidebar.multiselect("Flight / fare class", series_options, default=series_options[: min(5, len(series_options))])

    filtered = frame if not selected_series else frame[frame["series"].isin(selected_series)]
    latest_ts = filtered["timestamp"].max()
    latest_price = filtered.sort_values("timestamp").iloc[-1]["price"]
    chart_x = "departure_time" if filtered["departure_time"].notna().any() else "timestamp"
    chart_title = "Fare calendar by departure date" if chart_x == "departure_time" else "Fare movement over time"
    chart_x_title = "Departure date" if chart_x == "departure_time" else "Collected at"

    st.subheader("Fare Ticks")
    left_col, middle_col, right_col = st.columns(3)
    left_col.metric("Fare rows loaded", f"{len(filtered):,}")
    middle_col.metric("Latest fare scrape", latest_ts.strftime("%Y-%m-%d %H:%M:%S UTC"))
    right_col.metric("Latest fare", f"{latest_price:,.0f}")

    chart = px.line(
        filtered.sort_values(chart_x),
        x=chart_x,
        y="price",
        color="series",
        markers=True,
        title=chart_title,
    )
    chart.update_layout(height=520, xaxis_title=chart_x_title, yaxis_title="Price")
    st.plotly_chart(chart, use_container_width=True)

    st.dataframe(
        filtered.sort_values("timestamp", ascending=False),
        use_container_width=True,
        hide_index=True,
    )
else:
    if "example.com" in VNA_API_URL:
        st.info("Fare data is still empty because the scraper is using the example VNA endpoint in .env. Replace it with the real API request details to collect ticket prices.")
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
    st.caption(
        "Brent source: "
        f"{latest_fuel['brent_source']} | FX source: {latest_fuel['exchange_rate_source']} | "
        f"Mode: {latest_fuel['source_mode']}"
    )
    if pd.notna(latest_fuel["brent_price_timestamp"]):
        st.caption(f"Brent price timestamp: {latest_fuel['brent_price_timestamp'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
    if latest_fuel["source_note"]:
        st.info(str(latest_fuel["source_note"]))
    fallback_rows = int((fuel_frame["is_fallback"] == True).sum())
    unknown_rows = int(fuel_frame["is_fallback"].isna().sum())
    st.caption(f"Fallback rows loaded: {fallback_rows} | Legacy/unknown provenance rows: {unknown_rows}")

    fuel_sorted = fuel_frame.sort_values("timestamp")
    mode_colors = {"Live": "#117733", "Fallback": "#cc3311", "Unknown": "#767676"}

    jet_chart = go.Figure()
    jet_chart.add_trace(
        go.Scatter(
            x=fuel_sorted["timestamp"],
            y=fuel_sorted["jet_a1_est_vnd"],
            mode="lines",
            name="Jet A1 est.",
            line={"color": "#1f77b4", "width": 2},
        )
    )
    for source_mode, group in fuel_sorted.groupby("source_mode", dropna=False):
        label = str(source_mode)
        jet_chart.add_trace(
            go.Scatter(
                x=group["timestamp"],
                y=group["jet_a1_est_vnd"],
                mode="markers",
                name=f"{label} point",
                marker={"size": 8, "color": mode_colors.get(label, mode_colors["Unknown"])},
                customdata=group[["brent_source", "exchange_rate_source", "source_note"]].fillna("").values,
                hovertemplate=(
                    "Collected: %{x}<br>Jet A1: %{y:,.2f} VND/L<br>"
                    "Brent source: %{customdata[0]}<br>FX source: %{customdata[1]}<br>"
                    "Note: %{customdata[2]}<extra></extra>"
                ),
            )
        )
    jet_chart.update_layout(height=360, xaxis_title="Collected at", yaxis_title="VND/L")
    st.plotly_chart(jet_chart, use_container_width=True)

    fuel_cost_chart = go.Figure()
    fuel_cost_chart.add_trace(
        go.Scatter(
            x=fuel_sorted["timestamp"],
            y=fuel_sorted["han_sgn_fuel_cost"],
            mode="lines",
            name="HAN-SGN fuel cost",
            line={"color": "#6c5ce7", "width": 2},
        )
    )
    for source_mode, group in fuel_sorted.groupby("source_mode", dropna=False):
        label = str(source_mode)
        fuel_cost_chart.add_trace(
            go.Scatter(
                x=group["timestamp"],
                y=group["han_sgn_fuel_cost"],
                mode="markers",
                name=f"{label} point",
                marker={"size": 8, "color": mode_colors.get(label, mode_colors["Unknown"])},
                customdata=group[["brent_source", "exchange_rate_source", "source_note"]].fillna("").values,
                hovertemplate=(
                    "Collected: %{x}<br>Fuel cost: %{y:,.2f} VND<br>"
                    "Brent source: %{customdata[0]}<br>FX source: %{customdata[1]}<br>"
                    "Note: %{customdata[2]}<extra></extra>"
                ),
            )
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
