"""Transform cleaned CSV datasets into analytics-ready Power BI outputs.

Run from the backend directory:
    python etl/03_transform.py

This stage reads only data/processed/ and writes only data/analytics/.
It never writes to PostgreSQL, data/raw/, or data/processed/.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Dict

import pandas as pd


LOGGER = logging.getLogger("smart_waste_transform")
BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = BACKEND_DIR / "data" / "processed"
DEFAULT_OUTPUT_DIR = BACKEND_DIR / "data" / "analytics"

TABLES = [
    "users", "municipal_wards", "development_seed_citizen_wards", "areas", "waste_reports", "workers", "collection_requests",
    "segregation_ratings", "reward_transactions", "penalties", "complaints",
    "vehicles", "vehicle_locations", "alerts",
]
DATE_COLUMNS = {
    "users": ["created_at"],
    "waste_reports": ["reported_at"],
    "collection_requests": ["assigned_at", "collected_at"],
    "segregation_ratings": ["rated_at"],
    "complaints": ["created_at", "resolved_at"],
    "vehicle_locations": ["recorded_at"],
    "alerts": ["created_at"],
}

PRIORITY_WEIGHTS = {
    "waste_score": 0.30,
    "collection_score": 0.25,
    "segregation_score": 0.20,
    "complaint_score": 0.15,
    "population_score": 0.10,
}


def load_processed_tables(input_dir: Path) -> Dict[str, pd.DataFrame]:
    """Load all cleaned table CSVs and parse their date columns."""
    missing = [table for table in TABLES if not (input_dir / f"{table}.csv").exists()]
    if missing:
        raise FileNotFoundError(f"Missing cleaned CSV files in {input_dir}: {missing}")

    frames = {table: pd.read_csv(input_dir / f"{table}.csv") for table in TABLES}
    for table, columns in DATE_COLUMNS.items():
        for column in columns:
            frames[table][column] = pd.to_datetime(
                frames[table][column], errors="coerce"
            )
    return frames


def _as_int_column(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Int64")
    return frame


def _date_dimension(frames: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build a date dimension from dates present in cleaned operational data."""
    date_series = []
    for table, column in [
        ("users", "created_at"),
        ("waste_reports", "reported_at"),
        ("collection_requests", "assigned_at"),
        ("collection_requests", "collected_at"),
        ("segregation_ratings", "rated_at"),
        ("complaints", "created_at"),
        ("complaints", "resolved_at"),
        ("vehicle_locations", "recorded_at"),
        ("alerts", "created_at"),
    ]:
        date_series.append(frames[table][column].dropna().dt.normalize())
    dates = pd.concat(date_series, ignore_index=True).dropna()
    if dates.empty:
        return pd.DataFrame(columns=[
            "date_key", "date", "day", "month", "month_name", "quarter",
            "year", "day_of_week", "week", "is_weekend",
        ])
    dates = pd.date_range(dates.min(), dates.max(), freq="D")
    result = pd.DataFrame({"date": dates})
    result["date_key"] = result["date"].dt.strftime("%Y%m%d").astype("int64")
    result["day"] = result["date"].dt.day.astype("Int64")
    result["month"] = result["date"].dt.month.astype("Int64")
    result["month_name"] = result["date"].dt.month_name()
    result["quarter"] = "Q" + result["date"].dt.quarter.astype("string")
    result["year"] = result["date"].dt.year.astype("Int64")
    result["day_of_week"] = result["date"].dt.day_name()
    result["week"] = result["date"].dt.isocalendar().week.astype("Int64")
    result["is_weekend"] = result["date"].dt.dayofweek >= 5
    return result


def _build_facts(frames: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    area_ward = frames["areas"][["area_id", "ward_id"]]
    ward_labels = frames["municipal_wards"][
        ["ward_id", "ward_number", "ward_name", "population", "boundary_geojson"]
    ]
    waste = frames["waste_reports"].copy()
    waste = waste.merge(area_ward, on="area_id", how="left", validate="many_to_one")
    waste = waste.merge(
        ward_labels[["ward_id", "ward_number", "ward_name", "population"]],
        on="ward_id",
        how="left",
        validate="many_to_one",
    )
    waste["waste_date"] = waste["reported_at"].dt.date
    waste["waste_month"] = waste["reported_at"].dt.to_period("M").astype("string")
    waste["waste_year"] = waste["reported_at"].dt.year.astype("Int64")
    if "normalized_waste_type" not in waste:
        waste["normalized_waste_type"] = waste["waste_type"]
    fact_waste = waste[[
        "report_id", "citizen_id", "area_id", "ward_id", "ward_number",
        "ward_name", "population", "waste_type",
        "normalized_waste_type", "quantity_kg", "priority", "status",
        "reported_at", "waste_date", "waste_month", "waste_year",
    ]].copy()
    _as_int_column(fact_waste, ["report_id", "citizen_id", "area_id", "waste_year"])

    collection = frames["collection_requests"].copy()
    collection = collection.merge(
        waste[["report_id", "area_id", "ward_id", "ward_number"]],
        on="report_id",
        how="left",
        validate="many_to_one",
    )
    collection["collection_date"] = collection["collected_at"].dt.date
    collection["collection_duration_minutes"] = (
        collection["collected_at"] - collection["assigned_at"]
    ).dt.total_seconds() / 60
    collection["collection_status"] = collection["status"]
    fact_collection = collection[[
        "request_id", "report_id", "area_id", "ward_id", "ward_number",
        "worker_id", "assigned_at", "collected_at",
        "status", "collection_status", "collection_date",
        "collection_duration_minutes",
    ]].copy()
    _as_int_column(fact_collection, ["request_id", "report_id", "area_id", "ward_id", "worker_id"])

    complaint = frames["complaints"].copy()
    complaint = complaint.merge(area_ward, on="area_id", how="left", validate="many_to_one")
    complaint = complaint.merge(
        ward_labels[["ward_id", "ward_number"]],
        on="ward_id",
        how="left",
        validate="many_to_one",
    )
    complaint["complaint_date"] = complaint["created_at"].dt.date
    complaint["resolution_duration_hours"] = (
        complaint["resolved_at"] - complaint["created_at"]
    ).dt.total_seconds() / 3600
    complaint["complaint_status"] = complaint["status"]
    if "normalized_category" not in complaint:
        complaint["normalized_category"] = complaint["category"]
    fact_complaint = complaint[[
        "complaint_id", "citizen_id", "area_id", "ward_id", "ward_number",
        "category", "normalized_category",
        "priority", "status", "complaint_status", "created_at", "resolved_at",
        "complaint_date", "resolution_duration_hours",
    ]].copy()
    _as_int_column(fact_complaint, ["complaint_id", "citizen_id", "area_id", "ward_id"])

    rating = frames["segregation_ratings"].copy()
    rating["rating_category"] = rating["rating"].map({
        1: "Poor", 2: "Poor", 3: "Average", 4: "Good", 5: "Good",
    })
    fact_rating = rating[[
        "rating_id", "request_id", "citizen_id", "worker_id", "rating",
        "rating_category", "remarks", "rated_at",
    ]].copy()
    _as_int_column(fact_rating, ["rating_id", "request_id", "citizen_id", "worker_id", "rating"])
    fact_segmentation = fact_rating.merge(
        fact_collection[
            ["request_id", "report_id", "area_id", "ward_id", "ward_number"]
        ],
        on="request_id",
        how="left",
        validate="one_to_one",
    )

    fact_reward = frames["reward_transactions"].copy()
    _as_int_column(fact_reward, ["transaction_id", "citizen_id", "points", "reference_id"])
    fact_penalty = frames["penalties"].copy()
    _as_int_column(fact_penalty, ["penalty_id", "citizen_id"])
    fact_gps = frames["vehicle_locations"].copy()
    vehicle_area = frames["vehicles"][["vehicle_id", "worker_id"]].merge(
        frames["workers"][["worker_id", "assigned_area"]],
        on="worker_id",
        how="left",
        validate="many_to_one",
    ).rename(columns={"assigned_area": "area_id"})
    fact_gps = fact_gps.merge(
        vehicle_area[["vehicle_id", "worker_id", "area_id"]],
        on="vehicle_id",
        how="left",
        validate="many_to_one",
    ).merge(area_ward, on="area_id", how="left", validate="many_to_one")
    fact_gps = fact_gps.merge(
        ward_labels[["ward_id", "ward_number"]],
        on="ward_id",
        how="left",
        validate="many_to_one",
    )
    fact_gps["gps_date"] = fact_gps["recorded_at"].dt.date
    fact_gps["gps_hour"] = fact_gps["recorded_at"].dt.hour.astype("Int64")
    _as_int_column(fact_gps, ["location_id", "vehicle_id", "gps_hour"])
    fact_gps = fact_gps[[
        "location_id", "vehicle_id", "latitude", "longitude", "recorded_at",
        "gps_date", "gps_hour", "worker_id", "area_id", "ward_id",
        "ward_number",
    ]].sort_values(["vehicle_id", "recorded_at"])
    fact_alert = frames["alerts"].copy()
    fact_alert = fact_alert.merge(area_ward, on="area_id", how="left", validate="many_to_one")
    fact_alert = fact_alert.merge(
        ward_labels[["ward_id", "ward_number"]],
        on="ward_id",
        how="left",
        validate="many_to_one",
    )
    _as_int_column(fact_alert, ["alert_id", "area_id", "ward_id"])
    _as_int_column(fact_gps, ["worker_id", "area_id", "ward_id"])

    return {
        "fact_waste": fact_waste,
        "fact_collection": fact_collection,
        "fact_complaint": fact_complaint,
        "fact_rating": fact_rating,
        "fact_segmentation": fact_segmentation,
        "fact_reward": fact_reward,
        "fact_penalty": fact_penalty,
        "fact_gps": fact_gps,
        "fact_alert": fact_alert,
    }


def _build_dimensions(frames: Dict[str, pd.DataFrame], facts: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    users = frames["users"]
    wards = frames["municipal_wards"].copy()
    _as_int_column(wards, ["ward_id", "population"])
    wards["ward_key"] = wards["ward_id"]
    dim_ward = wards[[
        "ward_key", "ward_id", "ward_number", "ward_name", "zone",
        "population", "boundary_geojson",
    ]].copy()
    dim_area = frames["areas"].merge(
        wards[["ward_id", "ward_number", "ward_name", "population"]],
        on="ward_id",
        how="left",
        validate="many_to_one",
    )
    dim_area["is_provisional"] = dim_area["area_name"].astype("string").str.match(
        r"^Ward .+ - Operational Area \d+$", case=False, na=False
    )
    _as_int_column(dim_area, ["area_id"])
    workers = frames["workers"].merge(
        users[["user_id", "name"]], on="user_id", how="left", validate="many_to_one"
    ).rename(columns={"name": "worker_name"})
    dim_worker = workers[["worker_id", "user_id", "worker_name", "assigned_area"]].copy()
    _as_int_column(dim_worker, ["worker_id", "user_id", "assigned_area"])
    dim_citizen = users.loc[users["role"] == "CITIZEN"].rename(
        columns={"user_id": "citizen_id", "name": "citizen_name"}
    )[["citizen_id", "citizen_name", "email", "role", "created_at"]].copy()
    citizen_wards = frames["development_seed_citizen_wards"].merge(
        wards[["ward_id", "ward_number", "ward_name", "population"]],
        on="ward_id",
        how="left",
        validate="many_to_one",
    )
    dim_citizen = dim_citizen.merge(
        citizen_wards[
            ["citizen_id", "ward_id", "ward_number", "ward_name", "population"]
        ],
        on="citizen_id",
        how="left",
        validate="one_to_one",
    )
    _as_int_column(dim_citizen, ["citizen_id", "ward_id", "population"])
    dim_waste_type = pd.DataFrame({
        "waste_type": sorted(facts["fact_waste"]["normalized_waste_type"].dropna().unique())
    })
    dim_vehicle = frames["vehicles"].copy()
    _as_int_column(dim_vehicle, ["vehicle_id", "worker_id"])
    vehicle_columns = ["vehicle_id", "vehicle_number", "worker_id", "status"]
    dim_vehicle = dim_vehicle[vehicle_columns]
    return {
        "dim_date": _date_dimension(frames),
        "dim_ward": dim_ward,
        "dim_area": dim_area,
        "dim_worker": dim_worker,
        "dim_citizen": dim_citizen,
        "dim_waste_type": dim_waste_type,
        "dim_vehicle": dim_vehicle,
    }


def _build_worker_performance(frames: Dict[str, pd.DataFrame], fact_collection: pd.DataFrame) -> pd.DataFrame:
    worker_base = frames["workers"].merge(
        frames["users"][["user_id", "name"]], on="user_id", how="left", validate="many_to_one"
    ).rename(columns={"name": "worker_name"})
    independent = fact_collection.assign(
        collected=fact_collection["collection_status"].eq("COLLECTED")
    ).groupby("worker_id", as_index=False).agg(
        total_assigned=("request_id", "count"),
        total_collected=("collected", "sum"),
    )
    performance = worker_base[["worker_id", "worker_name"]].merge(
        independent, on="worker_id", how="left", validate="one_to_one"
    )
    performance[["total_assigned", "total_collected"]] = performance[[
        "total_assigned", "total_collected",
    ]].fillna(0).astype(int)
    performance["total_pending"] = performance["total_assigned"] - performance["total_collected"]
    performance["collection_efficiency"] = (
        100 * performance["total_collected"] /
        performance["total_assigned"].where(performance["total_assigned"] != 0)
    ).fillna(0).round(2)
    return performance[[
        "worker_id", "worker_name", "total_assigned", "total_collected",
        "total_pending", "collection_efficiency",
    ]].sort_values(["collection_efficiency", "total_assigned"], ascending=[False, False])


def _build_area_performance(frames: Dict[str, pd.DataFrame], facts: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    fact_waste = facts["fact_waste"]
    fact_collection = facts["fact_collection"]
    fact_complaint = facts["fact_complaint"]
    waste_area = fact_waste.groupby("area_id", as_index=False).agg(
        total_reports=("report_id", "count"),
        total_waste_kg=("quantity_kg", "sum"),
        avg_waste_per_report=("quantity_kg", "mean"),
    )
    collection_area = fact_collection.groupby("area_id", as_index=False).agg(
        total_collections=("request_id", "count"),
        pending_collections=("collection_status", lambda values: (values != "COLLECTED").sum()),
    )
    complaint_area = fact_complaint.groupby("area_id", as_index=False).agg(
        total_complaints=("complaint_id", "count"),
        open_complaints=("complaint_status", lambda values: (values == "OPEN").sum()),
    )
    result = frames["areas"][["area_id", "area_name"]].merge(
        waste_area, on="area_id", how="left"
    ).merge(collection_area, on="area_id", how="left").merge(
        complaint_area, on="area_id", how="left"
    )
    numeric_columns = [
        "total_reports", "total_waste_kg", "avg_waste_per_report",
        "total_collections", "pending_collections", "total_complaints",
        "open_complaints",
    ]
    result[numeric_columns] = result[numeric_columns].fillna(0)
    return result.sort_values("total_waste_kg", ascending=False)


def _build_ward_performance(
    frames: Dict[str, pd.DataFrame],
    facts: Dict[str, pd.DataFrame],
) -> pd.DataFrame:
    wards = frames["municipal_wards"][
        ["ward_id", "ward_number", "ward_name", "zone", "population"]
    ].copy()
    waste = facts["fact_waste"].groupby("ward_id", as_index=False).agg(
        report_count=("report_id", "count"),
        total_waste_kg=("quantity_kg", "sum"),
        average_kg_per_report=("quantity_kg", "mean"),
    )
    collections = facts["fact_collection"].groupby("ward_id", as_index=False).agg(
        collection_requests=("request_id", "count"),
        collected_requests=(
            "collection_status",
            lambda values: values.eq("COLLECTED").sum(),
        ),
        in_progress_requests=(
            "collection_status",
            lambda values: values.eq("IN_PROGRESS").sum(),
        ),
    )
    ratings = facts["fact_segmentation"].groupby("ward_id", as_index=False).agg(
        rating_count=("rating_id", "count"),
        average_segregation_rating=("rating", "mean"),
        good_ratings=("rating", lambda values: values.isin([4, 5]).sum()),
    )
    complaints = facts["fact_complaint"].groupby("ward_id", as_index=False).agg(
        complaint_count=("complaint_id", "count"),
        open_complaints=(
            "complaint_status",
            lambda values: values.eq("OPEN").sum(),
        ),
        resolved_complaints=(
            "complaint_status",
            lambda values: values.eq("RESOLVED").sum(),
        ),
    )
    result = (
        wards.merge(waste, on="ward_id", how="left", validate="one_to_one")
        .merge(collections, on="ward_id", how="left", validate="one_to_one")
        .merge(ratings, on="ward_id", how="left", validate="one_to_one")
        .merge(complaints, on="ward_id", how="left", validate="one_to_one")
    )
    count_columns = [
        "report_count",
        "collection_requests",
        "collected_requests",
        "in_progress_requests",
        "rating_count",
        "good_ratings",
        "complaint_count",
        "open_complaints",
        "resolved_complaints",
    ]
    result[count_columns] = result[count_columns].fillna(0).astype("int64")
    result[["total_waste_kg"]] = result[["total_waste_kg"]].fillna(0)
    result["average_kg_per_report"] = result["average_kg_per_report"].fillna(0)
    result["collection_efficiency_pct"] = (
        100 * result["collected_requests"]
        / result["collection_requests"].where(result["collection_requests"] > 0)
    )
    result["collection_coverage_pct"] = (
        100 * result["collection_requests"]
        / result["report_count"].where(result["report_count"] > 0)
    )
    result["good_segregation_rate_pct"] = (
        100 * result["good_ratings"]
        / result["rating_count"].where(result["rating_count"] > 0)
    )
    result["complaints_per_100_reports"] = (
        100 * result["complaint_count"]
        / result["report_count"].where(result["report_count"] > 0)
    )
    result["complaint_resolution_rate_pct"] = (
        100 * result["resolved_complaints"]
        / result["complaint_count"].where(result["complaint_count"] > 0)
    )
    result["population_daily_baseline_kg"] = (
        result["population"] * 0.45
    )
    return result.sort_values("ward_id")


def _normalize_score(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    low = numeric.min(skipna=True)
    high = numeric.max(skipna=True)
    if pd.isna(low) or pd.isna(high) or high == low:
        return pd.Series(0.0, index=values.index)
    return (100 * (numeric - low) / (high - low)).fillna(0).clip(0, 100)


def _build_priority_scores(ward_performance: pd.DataFrame) -> pd.DataFrame:
    scores = ward_performance.copy()
    scores["waste_score"] = _normalize_score(scores["total_waste_kg"])
    observed_collection = scores["collection_efficiency_pct"].notna()
    scores["collection_score"] = (
        100 - scores["collection_efficiency_pct"].fillna(0)
    ).clip(0, 100)
    observed_segregation = scores["good_segregation_rate_pct"].notna()
    scores["segregation_score"] = (
        100 - scores["good_segregation_rate_pct"].fillna(50)
    ).clip(0, 100)
    scores["complaint_score"] = _normalize_score(
        scores["complaints_per_100_reports"].fillna(0)
    )
    population_observed = scores["population"].notna()
    population_values = scores["population"].fillna(scores["population"].median())
    scores["population_score"] = _normalize_score(population_values)
    scores["priority_score"] = sum(
        scores[name] * weight
        for name, weight in PRIORITY_WEIGHTS.items()
    ).round(2)
    scores["priority_category"] = pd.cut(
        scores["priority_score"],
        bins=[-0.01, 30, 60, 80, 100],
        labels=["Low", "Medium", "High", "Critical"],
        include_lowest=True,
    ).astype("string")
    scores["collection_observed"] = observed_collection
    scores["segregation_observed"] = observed_segregation
    scores["population_observed"] = population_observed
    scores["priority_method"] = (
        "Min-max normalized within current extract; unobserved collection "
        "efficiency treated as zero, unobserved good-segregation rate as 50%."
    )
    return scores.sort_values(
        ["priority_score", "ward_id"],
        ascending=[False, True],
    )


def _build_ward_time_series(
    facts: Dict[str, pd.DataFrame],
    dimensions: Dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    waste = facts["fact_waste"].copy()
    waste["date"] = pd.to_datetime(waste["reported_at"]).dt.normalize()
    daily_waste = waste.groupby(["ward_id", "date"], as_index=False).agg(
        report_count=("report_id", "count"),
        total_waste_kg=("quantity_kg", "sum"),
        average_kg_per_report=("quantity_kg", "mean"),
    )
    collection = facts["fact_collection"].copy()
    collection["date"] = pd.to_datetime(collection["assigned_at"]).dt.normalize()
    collection = collection.dropna(subset=["date"])
    daily_collection = collection.groupby(["ward_id", "date"], as_index=False).agg(
        collection_count=("request_id", "count"),
        collected_count=(
            "collection_status",
            lambda values: values.eq("COLLECTED").sum(),
        ),
    )
    complaints = facts["fact_complaint"].copy()
    complaints["date"] = pd.to_datetime(complaints["created_at"]).dt.normalize()
    daily_complaints = complaints.groupby(["ward_id", "date"], as_index=False).agg(
        complaint_count=("complaint_id", "count")
    )
    ratings = facts["fact_segmentation"].copy()
    ratings["date"] = pd.to_datetime(ratings["rated_at"]).dt.normalize()
    daily_ratings = ratings.groupby(["ward_id", "date"], as_index=False).agg(
        rating_count=("rating_id", "count"),
        good_rating_count=("rating", lambda values: values.isin([4, 5]).sum()),
        average_rating=("rating", "mean"),
    )
    daily = (
        daily_waste.merge(
            daily_collection, on=["ward_id", "date"], how="outer",
            validate="one_to_one",
        )
        .merge(
            daily_complaints, on=["ward_id", "date"], how="outer",
            validate="one_to_one",
        )
        .merge(
            daily_ratings, on=["ward_id", "date"], how="outer",
            validate="one_to_one",
        )
        .sort_values(["ward_id", "date"])
    )
    daily["week_start"] = (
        daily["date"].dt.to_period("W-SUN").dt.start_time
    )
    daily["month"] = daily["date"].dt.to_period("M").astype("string")
    weekly = daily.groupby(["ward_id", "week_start"], as_index=False).agg(
        report_count=("report_count", "sum"),
        total_waste_kg=("total_waste_kg", "sum"),
        collection_count=("collection_count", "sum"),
        collected_count=("collected_count", "sum"),
        complaint_count=("complaint_count", "sum"),
    )
    monthly = daily.groupby(["ward_id", "month"], as_index=False).agg(
        report_count=("report_count", "sum"),
        total_waste_kg=("total_waste_kg", "sum"),
        collection_count=("collection_count", "sum"),
        collected_count=("collected_count", "sum"),
        complaint_count=("complaint_count", "sum"),
    )

    min_date = daily["date"].min()
    max_date = daily["date"].max()
    ward_ids = dimensions["dim_ward"]["ward_id"].dropna().astype("int64")
    calendar = pd.date_range(min_date, max_date, freq="D")
    index = pd.MultiIndex.from_product(
        [ward_ids, calendar],
        names=["ward_id", "date"],
    )
    features = daily.set_index(["ward_id", "date"]).reindex(index).reset_index()
    features = features.merge(
        dimensions["dim_ward"][["ward_id", "ward_number", "ward_name", "population"]],
        on="ward_id",
        how="left",
        validate="many_to_one",
    )
    for column in (
        "report_count",
        "total_waste_kg",
        "collection_count",
        "collected_count",
        "complaint_count",
        "rating_count",
        "good_rating_count",
    ):
        features[column] = features[column].fillna(0)
    features["day_of_week"] = features["date"].dt.dayofweek
    features["week"] = features["date"].dt.isocalendar().week.astype("Int64")
    features["month_number"] = features["date"].dt.month
    features["previous_day_waste_kg"] = features.groupby("ward_id")[
        "total_waste_kg"
    ].shift(1)
    features["previous_week_waste_kg"] = features.groupby("ward_id")[
        "total_waste_kg"
    ].shift(7)
    features["previous_day_collection_efficiency_pct"] = (
        100 * features.groupby("ward_id")["collected_count"].shift(1)
        / features.groupby("ward_id")["collection_count"].shift(1).replace(0, pd.NA)
    )
    features["previous_day_complaints"] = features.groupby("ward_id")[
        "complaint_count"
    ].shift(1)
    features["previous_day_good_segregation_rate_pct"] = (
        100 * features.groupby("ward_id")["good_rating_count"].shift(1)
        / features.groupby("ward_id")["rating_count"].shift(1).replace(0, pd.NA)
    )
    return daily, weekly, monthly, features


def _build_business_insights(
    ward_performance: pd.DataFrame,
    priority_scores: pd.DataFrame,
    waste_by_type: pd.DataFrame,
) -> pd.DataFrame:
    insights = []
    if not ward_performance.empty:
        top_waste = ward_performance.sort_values(
            "total_waste_kg", ascending=False
        ).iloc[0]
        insights.append({
            "topic": "Waste generation",
            "finding": f"Ward {top_waste['ward_number']} has the highest reported waste.",
            "evidence": (
                f"{top_waste['total_waste_kg']:.2f} kg from "
                f"{int(top_waste['report_count'])} reports."
            ),
            "operational_issue": (
                f"Collection efficiency is {top_waste['collection_efficiency_pct']:.2f}%."
                if pd.notna(top_waste["collection_efficiency_pct"])
                else "No collection requests are recorded for this ward."
            ),
            "recommendation": (
                "Review collection capacity and schedules against the observed "
                "reported volume; this is a candidate for operational review."
            ),
        })
        observed = ward_performance.dropna(subset=["collection_efficiency_pct"])
        if not observed.empty:
            worst_collection = observed.sort_values(
                ["collection_efficiency_pct", "collection_requests"],
                ascending=[True, False],
            ).iloc[0]
            insights.append({
                "topic": "Collection performance",
                "finding": (
                    f"Ward {worst_collection['ward_number']} has the lowest "
                    "observed collection efficiency."
                ),
                "evidence": (
                    f"{int(worst_collection['collected_requests'])} collected of "
                    f"{int(worst_collection['collection_requests'])} requests "
                    f"({worst_collection['collection_efficiency_pct']:.2f}%)."
                ),
                "operational_issue": (
                    f"{int(worst_collection['collection_requests'] - worst_collection['collected_requests'])} "
                    "requests are not collected."
                ),
                "recommendation": (
                    "Review assignment capacity and outstanding requests in this "
                    "ward before changing service schedules."
                ),
            })
        observed_segregation = ward_performance.dropna(
            subset=["good_segregation_rate_pct"]
        )
        if not observed_segregation.empty:
            worst_segregation = observed_segregation.sort_values(
                ["good_segregation_rate_pct", "rating_count"],
                ascending=[True, False],
            ).iloc[0]
            insights.append({
                "topic": "Segregation",
                "finding": (
                    f"Ward {worst_segregation['ward_number']} has the lowest "
                    "observed good-segregation rate."
                ),
                "evidence": (
                    f"{worst_segregation['good_segregation_rate_pct']:.2f}% "
                    f"good ratings from {int(worst_segregation['rating_count'])} ratings."
                ),
                "operational_issue": (
                    f"Average rating is "
                    f"{worst_segregation['average_segregation_rating']:.2f}/5."
                ),
                "recommendation": (
                    "Review resident guidance and collection feedback in this ward; "
                    "do not infer causes from ratings alone."
                ),
            })
        top_complaints = ward_performance.sort_values(
            ["complaint_count", "ward_id"],
            ascending=[False, True],
        ).iloc[0]
        insights.append({
            "topic": "Complaints",
            "finding": f"Ward {top_complaints['ward_number']} has the most complaints.",
            "evidence": (
                f"{int(top_complaints['complaint_count'])} complaints across "
                f"{int(top_complaints['report_count'])} reports."
            ),
            "operational_issue": (
                f"{int(top_complaints['open_complaints'])} complaints are open."
            ),
            "recommendation": (
                "Inspect complaint categories and linked service events before "
                "deploying a ward-specific intervention."
            ),
        })
    if not priority_scores.empty:
        critical = priority_scores.loc[
            priority_scores["priority_category"].eq("Critical")
        ]
        if not critical.empty:
            names = ", ".join(
                f"Ward {row.ward_number}"
                for row in critical.head(5).itertuples()
            )
            insights.append({
                "topic": "Priority",
                "finding": f"{len(critical)} wards score as Critical under the development model.",
                "evidence": (
                    f"Highest-ranked wards include {names}; score uses the "
                    "documented 30/25/20/15/10 component weights."
                ),
                "operational_issue": (
                    "This score combines normalized indicators and is not an "
                    "official municipal standard."
                ),
                "recommendation": (
                    "Use the ranking to prioritize a human review of workload, "
                    "coverage, segregation, and complaint evidence."
                ),
            })
    if not waste_by_type.empty:
        largest_type = waste_by_type.iloc[0]
        insights.append({
            "topic": "Waste composition",
            "finding": f"{largest_type['normalized_waste_type']} is the largest type by reported kg.",
            "evidence": (
                f"{largest_type['total_waste_kg']:.2f} kg from "
                f"{int(largest_type['report_count'])} reports."
            ),
            "operational_issue": (
                "Composition is based on submitted report labels, not independent "
                "waste audits."
            ),
            "recommendation": (
                "Use observed type mix to plan pilot handling capacity and validate "
                "it against field audit data."
            ),
        })
    return pd.DataFrame(
        insights,
        columns=[
            "topic",
            "finding",
            "evidence",
            "operational_issue",
            "recommendation",
        ],
    )


def _build_aggregates(frames: Dict[str, pd.DataFrame], facts: Dict[str, pd.DataFrame], dimensions: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    fact_waste = facts["fact_waste"]
    fact_collection = facts["fact_collection"]
    fact_complaint = facts["fact_complaint"]
    fact_rating = facts["fact_rating"]
    fact_reward = facts["fact_reward"]
    fact_penalty = facts["fact_penalty"]
    fact_alert = facts["fact_alert"]

    waste_by_type = fact_waste.groupby("normalized_waste_type", as_index=False).agg(
        report_count=("report_id", "count"),
        total_waste_kg=("quantity_kg", "sum"),
        average_waste_kg=("quantity_kg", "mean"),
    ).sort_values("total_waste_kg", ascending=False)
    waste_by_area = fact_waste.groupby("area_id", as_index=False).agg(
        report_count=("report_id", "count"),
        total_waste_kg=("quantity_kg", "sum"),
        average_waste_kg=("quantity_kg", "mean"),
    ).merge(dimensions["dim_area"][["area_id", "area_name"]], on="area_id", how="left").sort_values("total_waste_kg", ascending=False)
    daily_waste = fact_waste.dropna(subset=["waste_date"]).groupby("waste_date", as_index=False).agg(
        report_count=("report_id", "count"), total_waste_kg=("quantity_kg", "sum"), average_waste_kg=("quantity_kg", "mean")
    )
    monthly_waste = fact_waste.dropna(subset=["waste_month"]).groupby("waste_month", as_index=False).agg(
        report_count=("report_id", "count"), total_waste_kg=("quantity_kg", "sum"), average_waste_kg=("quantity_kg", "mean")
    )
    complaint_analytics = fact_complaint.groupby(
        ["area_id", "normalized_category", "priority", "complaint_status"], dropna=False, as_index=False
    ).agg(complaint_count=("complaint_id", "count"), open_complaints=("complaint_status", lambda values: (values == "OPEN").sum()), resolved_complaints=("complaint_status", lambda values: (values == "RESOLVED").sum()))
    complaint_analytics = complaint_analytics.merge(dimensions["dim_area"][["area_id", "area_name"]], on="area_id", how="left")
    collection_status = fact_collection.groupby("collection_status", as_index=False).agg(request_count=("request_id", "count")).rename(columns={"collection_status": "status"})
    collection_area = fact_collection.groupby("area_id", as_index=False).agg(
        total_collections=("request_id", "count"), pending_collections=("collection_status", lambda values: (values != "COLLECTED").sum()), collected_collections=("collection_status", lambda values: (values == "COLLECTED").sum())
    ).merge(dimensions["dim_area"][["area_id", "area_name"]], on="area_id", how="left")
    rating_summary = fact_rating.groupby("rating_category", as_index=False).agg(rating_count=("rating_id", "count"), average_rating=("rating", "mean"))
    reward_summary = fact_reward.groupby("citizen_id", as_index=False).agg(total_reward_points=("points", "sum"), transaction_count=("transaction_id", "count"))
    penalty_summary = fact_penalty.groupby("citizen_id", as_index=False).agg(total_penalty_amount=("amount", "sum"), penalty_count=("penalty_id", "count"))
    alert_summary = fact_alert.groupby(["alert_type", "severity", "status"], as_index=False).agg(alert_count=("alert_id", "count"))
    return {
        "analytics_waste_by_type": waste_by_type,
        "analytics_waste_by_area": waste_by_area,
        "analytics_daily_waste": daily_waste,
        "analytics_monthly_waste": monthly_waste,
        "analytics_complaints": complaint_analytics,
        "analytics_collection_status": collection_status,
        "analytics_collection_by_area": collection_area,
        "analytics_rating_summary": rating_summary,
        "analytics_reward_summary": reward_summary,
        "analytics_penalty_summary": penalty_summary,
        "analytics_alert_summary": alert_summary,
    }


def _validate_outputs(frames: Dict[str, pd.DataFrame], facts: Dict[str, pd.DataFrame], aggregates: Dict[str, pd.DataFrame]) -> list[str]:
    discrepancies = []
    expected_facts = {
        "waste_reports": "fact_waste", "collection_requests": "fact_collection", "complaints": "fact_complaint",
        "segregation_ratings": "fact_rating", "reward_transactions": "fact_reward", "penalties": "fact_penalty",
        "vehicle_locations": "fact_gps", "alerts": "fact_alert",
    }
    for source, fact in expected_facts.items():
        if len(frames[source]) != len(facts[fact]):
            discrepancies.append(f"{fact} row count {len(facts[fact])} != {source} {len(frames[source])}")
    if len(frames["segregation_ratings"]) != len(facts["fact_segmentation"]):
        discrepancies.append(
            "fact_segmentation row count "
            f"{len(facts['fact_segmentation'])} != segregation_ratings "
            f"{len(frames['segregation_ratings'])}"
        )
    if facts["fact_segmentation"]["ward_id"].isna().any():
        discrepancies.append("segmentation fact contains ratings without a ward")
    total_checks = [
        ("waste kg", frames["waste_reports"]["quantity_kg"].sum(), facts["fact_waste"]["quantity_kg"].sum()),
        ("collection count", len(frames["collection_requests"]), len(facts["fact_collection"])),
        ("complaint count", len(frames["complaints"]), len(facts["fact_complaint"])),
        ("reward points", frames["reward_transactions"]["points"].sum(), facts["fact_reward"]["points"].sum()),
        ("penalty amount", frames["penalties"]["amount"].sum(), facts["fact_penalty"]["amount"].sum()),
    ]
    for name, before, after in total_checks:
        if not pd.isna(before) and not pd.isna(after) and abs(float(before) - float(after)) > 0.01:
            discrepancies.append(f"{name} {before} != {after}")
    area = aggregates["analytics_waste_by_area"]
    if abs(area["total_waste_kg"].sum() - facts["fact_waste"]["quantity_kg"].sum()) > 0.01:
        discrepancies.append("area waste aggregate has fan-out discrepancy")
    if area["report_count"].sum() != len(facts["fact_waste"]):
        discrepancies.append("area report aggregate has fan-out discrepancy")
    collection_by_area = aggregates["analytics_collection_by_area"]
    if collection_by_area["total_collections"].sum() != len(facts["fact_collection"]):
        discrepancies.append("area collection aggregate has fan-out discrepancy")
    complaints = aggregates["analytics_complaints"]
    if complaints["complaint_count"].sum() != len(facts["fact_complaint"]):
        discrepancies.append("complaint aggregate has fan-out discrepancy")
    ward_performance = aggregates["analytics_ward_performance"]
    if len(ward_performance) != len(frames["municipal_wards"]):
        discrepancies.append("ward performance does not contain every municipal ward")
    if ward_performance["report_count"].sum() != len(facts["fact_waste"]):
        discrepancies.append("ward report aggregate has fan-out discrepancy")
    if abs(
        ward_performance["total_waste_kg"].sum()
        - facts["fact_waste"]["quantity_kg"].sum()
    ) > 0.01:
        discrepancies.append("ward waste aggregate has fan-out discrepancy")
    return discrepancies


def transform_tables(frames: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """Compatibility API: transform already-loaded cleaned frames in memory."""
    facts = _build_facts(frames)
    dimensions = _build_dimensions(frames, facts)
    worker = _build_worker_performance(frames, facts["fact_collection"])
    area = _build_area_performance(frames, facts)
    aggregates = _build_aggregates(frames, facts, dimensions)
    ward_performance = _build_ward_performance(frames, facts)
    priority_scores = _build_priority_scores(ward_performance)
    daily, weekly, monthly, forecast_features = _build_ward_time_series(
        facts,
        dimensions,
    )
    insights = _build_business_insights(
        ward_performance,
        priority_scores,
        aggregates["analytics_waste_by_type"],
    )
    daily_global = daily.groupby("date", as_index=False).agg(
        report_count=("report_count", "sum"),
        total_waste_kg=("total_waste_kg", "sum"),
        collection_count=("collection_count", "sum"),
        collected_count=("collected_count", "sum"),
        complaint_count=("complaint_count", "sum"),
    )
    weekly_global = weekly.groupby("week_start", as_index=False).agg(
        report_count=("report_count", "sum"),
        total_waste_kg=("total_waste_kg", "sum"),
        collection_count=("collection_count", "sum"),
        collected_count=("collected_count", "sum"),
        complaint_count=("complaint_count", "sum"),
    )
    monthly_global = monthly.groupby("month", as_index=False).agg(
        report_count=("report_count", "sum"),
        total_waste_kg=("total_waste_kg", "sum"),
        collection_count=("collection_count", "sum"),
        collected_count=("collected_count", "sum"),
        complaint_count=("complaint_count", "sum"),
    )
    daily_global["collection_efficiency_pct"] = (
        100 * daily_global["collected_count"]
        / daily_global["collection_count"].where(
            daily_global["collection_count"] > 0
        )
    )
    weekly_global["collection_efficiency_pct"] = (
        100 * weekly_global["collected_count"]
        / weekly_global["collection_count"].where(
            weekly_global["collection_count"] > 0
        )
    )
    monthly_global["collection_efficiency_pct"] = (
        100 * monthly_global["collected_count"]
        / monthly_global["collection_count"].where(
            monthly_global["collection_count"] > 0
        )
    )
    ward_overview = priority_scores.merge(
        dimensions["dim_ward"][["ward_id", "boundary_geojson"]],
        on="ward_id",
        how="left",
        validate="one_to_one",
    )
    area_operations = area.merge(
        frames["areas"][["area_id", "ward_id", "status", "locality_name"]],
        on="area_id",
        how="left",
        validate="one_to_one",
    ).merge(
        dimensions["dim_ward"][["ward_id", "ward_number", "ward_name"]],
        on="ward_id",
        how="left",
        validate="many_to_one",
    )
    worker_report = worker.merge(
        frames["workers"][["worker_id", "assigned_area"]],
        on="worker_id",
        how="left",
        validate="one_to_one",
    ).merge(
        dimensions["dim_area"][["area_id", "area_name", "ward_id", "ward_number"]],
        left_on="assigned_area",
        right_on="area_id",
        how="left",
        validate="many_to_one",
    )
    priority_output_columns = [
        "ward_id", "ward_number", "ward_name", "population", "report_count",
        "total_waste_kg", "average_kg_per_report", "collection_requests",
        "collected_requests", "collection_efficiency_pct",
        "collection_coverage_pct", "rating_count",
        "good_segregation_rate_pct", "average_segregation_rating",
        "complaint_count", "complaints_per_100_reports",
        "waste_score", "collection_score", "segregation_score",
        "complaint_score", "population_score", "priority_score",
        "priority_category", "collection_observed", "segregation_observed",
        "population_observed", "priority_method",
    ]
    outputs = {
        **facts,
        **dimensions,
        "analytics_worker_performance": worker,
        "analytics_area_performance": area,
        "analytics_ward_performance": ward_performance,
        "analytics_ward_priority_score": priority_scores[priority_output_columns],
        "analytics_business_insights": insights,
        "analytics_ward_daily": daily,
        "analytics_ward_weekly": weekly,
        "analytics_ward_monthly": monthly,
        "analytics_forecast_features": forecast_features,
        **aggregates,
        "powerbi_ward_overview": ward_overview,
        "powerbi_ward_map": ward_overview[[
            "ward_id", "ward_number", "ward_name", "boundary_geojson",
            "total_waste_kg", "collection_efficiency_pct",
            "good_segregation_rate_pct", "complaint_count",
            "priority_score", "priority_category",
        ]],
        "powerbi_daily_trends": daily_global,
        "powerbi_weekly_trends": weekly_global,
        "powerbi_monthly_trends": monthly_global,
        "powerbi_waste_type": aggregates["analytics_waste_by_type"],
        "powerbi_area_operations": area_operations,
        "powerbi_worker_performance": worker_report,
    }
    discrepancies = _validate_outputs(
        frames,
        facts,
        {**aggregates, "analytics_ward_performance": ward_performance},
    )
    if discrepancies:
        raise RuntimeError(
            "Transformation validation failed: " + "; ".join(discrepancies)
        )
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Transform cleaned Smart Waste CSVs into analytics datasets")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    LOGGER.info("Transformation started; input=%s", args.input_dir)
    frames = load_processed_tables(args.input_dir)
    all_outputs = transform_tables(frames)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in all_outputs.items():
        output_file = args.output_dir / f"{name}.csv"
        frame.to_csv(output_file, index=False)
        LOGGER.info("Output dataset=%s rows=%d file=%s", name, len(frame), output_file)
    LOGGER.info("Row-count, totals, and fan-out validation passed")
    print("====================================")
    print("SMART WASTE TRANSFORMATION COMPLETE")
    print("====================================")
    print(f"Input directory: {args.input_dir}")
    print(f"Output datasets: {len(all_outputs)}")
    print(f"Output directory: {args.output_dir}")
    print("Validation: row counts, totals, and fan-out checks passed")


if __name__ == "__main__":
    main()
