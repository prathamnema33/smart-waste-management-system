"""Read-only exploratory data analysis for the Smart Waste Management database.

Run from the backend directory:
    python eda.py

Outputs are written to eda_output/ by default. The script never inserts,
updates, deletes, or creates database objects.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import inspect, text

from database import engine


TABLES = [
    "users",
    "municipal_wards",
    "development_seed_citizen_wards",
    "areas",
    "waste_reports",
    "workers",
    "collection_requests",
    "segregation_ratings",
    "reward_transactions",
    "penalties",
    "complaints",
    "vehicles",
    "vehicle_locations",
    "alerts",
]

CATEGORICAL_COLUMNS = {
    "users": ["role"],
    "waste_reports": ["waste_type", "priority", "status"],
    "collection_requests": ["status"],
    "complaints": ["category", "priority", "status"],
    "segregation_ratings": ["rating"],
    "penalties": ["status"],
    "vehicles": ["status"],
    "alerts": ["alert_type", "severity", "status"],
}

DATE_COLUMNS = {
    "users": ["created_at"],
    "waste_reports": ["reported_at"],
    "collection_requests": ["assigned_at", "collected_at"],
    "segregation_ratings": ["rated_at"],
    "complaints": ["created_at", "resolved_at"],
    "vehicle_locations": ["recorded_at"],
    "alerts": ["created_at"],
}

ALLOWED_VALUES = {
    "waste_reports.waste_type": {"Plastic", "Organic", "Paper", "Glass", "Metal", "E-Waste", "Mixed", "Other"},
    "waste_reports.priority": {"LOW", "NORMAL", "HIGH", "URGENT"},
    "waste_reports.status": {"PENDING", "ASSIGNED", "COLLECTED"},
    "collection_requests.status": {"ASSIGNED", "IN_PROGRESS", "COLLECTED"},
    "complaints.category": {"MISSED_COLLECTION", "ILLEGAL_DUMPING", "OVERFLOWING_BIN", "WORKER_ISSUE", "SEGREGATION", "OTHER"},
    "complaints.priority": {"LOW", "NORMAL", "HIGH", "URGENT"},
    "complaints.status": {"OPEN", "IN_PROGRESS", "RESOLVED"},
    "penalties.status": {"PENDING", "PAID"},
    "vehicles.status": {"ACTIVE", "INACTIVE", "MAINTENANCE"},
    "alerts.alert_type": {"HIGH_WASTE", "PENDING_COLLECTION", "REPEATED_COMPLAINTS", "VEHICLE_INACTIVE", "POOR_SEGREGATION", "ILLEGAL_DUMPING", "UNASSIGNED_COLLECTION_DEMAND"},
    "alerts.severity": {"LOW", "MEDIUM", "HIGH", "CRITICAL"},
    "alerts.status": {"OPEN", "RESOLVED"},
}


def load_tables() -> dict[str, pd.DataFrame]:
    with engine.connect() as connection:
        return {
            table: pd.read_sql_query(text(f'SELECT * FROM "{table}"'), connection)
            for table in TABLES
        }


def database_overview(frames: dict[str, pd.DataFrame]) -> list[str]:
    inspector = inspect(engine)
    lines = ["## 1. Data Overview", "", "| Table | Rows | Columns | Primary key |", "|---|---:|---:|---|"]
    for table, frame in frames.items():
        primary_keys = inspector.get_pk_constraint(table).get("constrained_columns", [])
        lines.append(f"| {table} | {len(frame):,} | {len(frame.columns)} | {', '.join(primary_keys)} |")
    lines += ["", "Foreign keys:", ""]
    for table in TABLES:
        for foreign_key in inspector.get_foreign_keys(table):
            lines.append(
                f"- `{table}.{', '.join(foreign_key['constrained_columns'])}` -> "
                f"`{foreign_key['referred_table']}.{', '.join(foreign_key['referred_columns'])}`"
            )
    lines += ["", "Date/time, numeric, and categorical columns are listed in the generated CSV summaries."]
    return lines


def quality_analysis(frames: dict[str, pd.DataFrame]) -> tuple[list[str], pd.DataFrame]:
    issues: list[dict[str, Any]] = []

    def add(issue: str, table: str, count: int, detection: str, treatment: str):
        if count:
            issues.append({"issue": issue, "table": table, "count": int(count), "detection": detection, "etl_treatment": treatment})

    for table, frame in frames.items():
        null_count = int(frame.isna().sum().sum())
        add("Missing values", table, null_count, "DataFrame.isna().sum()", "Preserve intentional nulls; quarantine required-field nulls.")
        duplicate_count = int(frame.duplicated().sum())
        add("Duplicate full rows", table, duplicate_count, "DataFrame.duplicated()", "Deduplicate only after confirming the business key.")

    citizens = set(
        frames["users"].loc[frames["users"]["role"].eq("CITIZEN"), "user_id"]
    )
    citizen_mapping = frames["development_seed_citizen_wards"]
    mapped_citizens = set(citizen_mapping["citizen_id"].dropna())
    invalid_mapping_count = (
        len(citizens - mapped_citizens)
        + len(mapped_citizens - citizens)
        + int(citizen_mapping["citizen_id"].duplicated(keep=False).sum())
    )
    add(
        "Invalid citizen home-ward coverage",
        "development_seed_citizen_wards",
        invalid_mapping_count,
        "Every citizen has one unique mapping to a municipal ward",
        "Reconcile mappings without changing municipal ward records.",
    )

    waste = frames["waste_reports"]
    add("Negative or zero waste quantity", "waste_reports", int((waste["quantity_kg"] <= 0).sum()), "quantity_kg <= 0", "Quarantine invalid quantities; do not silently coerce.")
    add("Invalid report coordinates", "waste_reports", int(((~waste["latitude"].between(-90, 90)) | (~waste["longitude"].between(-180, 180))).sum()), "latitude/longitude bounds", "Quarantine invalid GPS records.")
    gps = frames["vehicle_locations"]
    add("Invalid GPS coordinates", "vehicle_locations", int(((~gps["latitude"].between(-90, 90)) | (~gps["longitude"].between(-180, 180))).sum()), "latitude/longitude bounds", "Quarantine invalid GPS records.")

    for key, allowed in ALLOWED_VALUES.items():
        table, column = key.split(".")
        invalid = ~frames[table][column].isin(allowed) & frames[table][column].notna()
        add(f"Invalid categorical value in {column}", table, int(invalid.sum()), f"{column} not in controlled domain", "Map known variants; quarantine unknown values.")

    type_labels = waste["waste_type"].dropna().astype("string")
    casefolded = type_labels.str.casefold()
    spelling_counts = type_labels.groupby(casefolded).nunique()
    varying_case = int(casefolded.map(spelling_counts).gt(1).sum())
    add("Inconsistent waste capitalization", "waste_reports", varying_case, "multiple spellings within a case-insensitive category", "Normalize categories to a controlled dimension.")
    requests = frames["collection_requests"]
    add("Collected request missing collected_at", "collection_requests", int(((requests["status"] == "COLLECTED") & requests["collected_at"].isna()).sum()), "status = COLLECTED and collected_at IS NULL", "Reject or repair before warehouse loading.")
    add("Collected request before assigned_at", "collection_requests", int((requests["collected_at"] < requests["assigned_at"]).fillna(False).sum()), "collected_at < assigned_at", "Quarantine timestamp sequence errors.")
    complaints = frames["complaints"]
    add("Resolved complaint missing resolved_at", "complaints", int(((complaints["status"] == "RESOLVED") & complaints["resolved_at"].isna()).sum()), "status = RESOLVED and resolved_at IS NULL", "Repair from audit data or retain unresolved flag.")
    add("Unresolved complaint has resolved_at", "complaints", int(((complaints["status"] != "RESOLVED") & complaints["resolved_at"].notna()).sum()), "non-resolved status with resolved_at", "Reconcile status and timestamp.")

    issue_frame = pd.DataFrame(issues, columns=["issue", "table", "count", "detection", "etl_treatment"])
    lines = ["## 2. Data Quality", "", "| Issue | Table | Count | Detection | ETL treatment |", "|---|---|---:|---|---|"]
    if issue_frame.empty:
        lines.append("| No issues detected | - | 0 | - | - |")
    else:
        for row in issue_frame.itertuples(index=False):
            lines.append(f"| {row.issue} | {row.table} | {row.count:,} | {row.detection} | {row.etl_treatment} |")
    return lines, issue_frame


def save_univariate(frames: dict[str, pd.DataFrame], output: Path) -> list[str]:
    summaries = []
    for table, columns in CATEGORICAL_COLUMNS.items():
        for column in columns:
            summary = frames[table][column].value_counts(dropna=False).rename_axis(column).reset_index(name="count")
            summary.insert(0, "table", table)
            summary.to_csv(output / f"{table}_{column}_distribution.csv", index=False)
            summaries.append(f"- `{table}.{column}` distribution saved to CSV.")
    waste = frames["waste_reports"]["quantity_kg"].describe(percentiles=[.25, .5, .75]).to_frame("quantity_kg")
    waste.to_csv(output / "waste_quantity_summary.csv")
    frames["waste_reports"]["quantity_kg"].plot(kind="hist", bins=30, title="Waste quantity distribution")
    plt.xlabel("kg")
    plt.tight_layout()
    plt.savefig(output / "waste_quantity_distribution.png")
    plt.close()
    return ["## 3. Univariate Analysis", "", *summaries, "- Waste quantity statistics and histogram were generated."]


def save_bivariate(frames: dict[str, pd.DataFrame], output: Path) -> list[str]:
    waste = frames["waste_reports"]
    by_type = waste.groupby("waste_type", dropna=False).agg(total_reports=("report_id", "count"), total_waste_kg=("quantity_kg", "sum"), average_waste_kg=("quantity_kg", "mean")).sort_values("total_waste_kg", ascending=False)
    by_type.to_csv(output / "waste_by_type.csv")
    by_type["total_waste_kg"].plot(kind="bar", title="Waste by type")
    plt.ylabel("kg")
    plt.tight_layout()
    plt.savefig(output / "waste_by_type.png")
    plt.close()
    area = waste.groupby("area_id").agg(total_reports=("report_id", "count"), total_waste_kg=("quantity_kg", "sum"), average_waste_kg=("quantity_kg", "mean")).sort_values("total_waste_kg", ascending=False)
    area.to_csv(output / "waste_by_area.csv")
    report_area = waste[["report_id", "area_id"]].merge(
        frames["areas"][["area_id", "ward_id"]], on="area_id", how="left",
        validate="many_to_one",
    )
    by_ward_type = waste.merge(
        report_area[["report_id", "ward_id"]], on="report_id", how="left",
        validate="one_to_one",
    ).groupby(["ward_id", "waste_type"], dropna=False, as_index=False).agg(
        report_count=("report_id", "count"),
        total_waste_kg=("quantity_kg", "sum"),
    )
    by_ward_type.to_csv(output / "waste_by_ward_and_type.csv", index=False)
    return ["## 4. Bivariate Analysis", "", "- Waste-by-type, area, and ward/type summaries were generated.", "- Collection, rating, complaint, and waste metrics are aggregated independently by ward to prevent join fan-out."]


def ward_performance(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build ward metrics from separate aggregates to avoid join multiplication."""
    area_ward = frames["areas"][["area_id", "ward_id"]]
    reports = frames["waste_reports"].merge(
        area_ward, on="area_id", how="left", validate="many_to_one"
    )
    waste = reports.groupby("ward_id", as_index=False).agg(
        report_count=("report_id", "count"),
        total_waste_kg=("quantity_kg", "sum"),
        average_kg_per_report=("quantity_kg", "mean"),
        first_report_at=("reported_at", "min"),
        last_report_at=("reported_at", "max"),
    )
    waste["observed_period_days"] = (
        waste["last_report_at"] - waste["first_report_at"]
    ).dt.days.add(1).clip(lower=1)
    waste["approx_daily_waste_kg"] = (
        waste["total_waste_kg"] / waste["observed_period_days"]
    )

    request_rows = frames["collection_requests"].merge(
        reports[["report_id", "ward_id"]], on="report_id", how="left",
        validate="many_to_one",
    )
    collection = request_rows.groupby("ward_id", as_index=False).agg(
        collection_requests=("request_id", "count"),
        collected_requests=("status", lambda values: values.eq("COLLECTED").sum()),
    )

    rating_rows = frames["segregation_ratings"].merge(
        request_rows[["request_id", "report_id", "worker_id", "ward_id"]],
        on="request_id", how="left", validate="one_to_one",
        suffixes=("", "_request"),
    )
    rating_rows = rating_rows.loc[
        rating_rows["citizen_id"].eq(
            rating_rows["report_id"].map(
                reports.set_index("report_id")["citizen_id"]
            )
        )
        & rating_rows["worker_id"].eq(rating_rows["worker_id_request"])
    ]
    ratings = rating_rows.groupby("ward_id", as_index=False).agg(
        rating_count=("rating_id", "count"),
        average_segregation_rating=("rating", "mean"),
        good_ratings=("rating", lambda values: values.isin([4, 5]).sum()),
    )

    complaints = frames["complaints"].merge(
        area_ward, on="area_id", how="left", validate="many_to_one"
    ).groupby("ward_id", as_index=False).agg(
        complaint_count=("complaint_id", "count"),
    )
    result = (
        frames["municipal_wards"][
            ["ward_id", "ward_number", "ward_name", "population"]
        ]
        .merge(waste, on="ward_id", how="left", validate="one_to_one")
        .merge(collection, on="ward_id", how="left", validate="one_to_one")
        .merge(ratings, on="ward_id", how="left", validate="one_to_one")
        .merge(complaints, on="ward_id", how="left", validate="one_to_one")
    )
    for column in (
        "report_count", "collection_requests", "collected_requests",
        "rating_count", "good_ratings", "complaint_count",
    ):
        result[column] = result[column].fillna(0).astype("int64")
    for column in ("total_waste_kg", "average_kg_per_report", "approx_daily_waste_kg"):
        result[column] = result[column].fillna(0)
    result["collection_efficiency_pct"] = (
        100 * result["collected_requests"]
        / result["collection_requests"].where(result["collection_requests"] > 0)
    )
    result["good_segregation_rate_pct"] = (
        100 * result["good_ratings"]
        / result["rating_count"].where(result["rating_count"] > 0)
    )
    result["population_daily_baseline_kg"] = result["population"] * 0.45
    return result.sort_values("ward_id")


def save_time_analysis(frames: dict[str, pd.DataFrame], output: Path) -> list[str]:
    waste = frames["waste_reports"].dropna(subset=["reported_at"]).copy()
    waste["date"] = waste["reported_at"].dt.date
    daily = waste.groupby("date").agg(total_reports=("report_id", "count"), total_waste_kg=("quantity_kg", "sum"))
    daily.to_csv(output / "daily_waste.csv")
    monthly = waste.assign(month=waste["reported_at"].dt.to_period("M")).groupby("month").agg(total_reports=("report_id", "count"), total_waste_kg=("quantity_kg", "sum"))
    monthly.to_csv(output / "monthly_waste.csv")
    daily["total_waste_kg"].plot(title="Daily waste generation", figsize=(10, 4))
    plt.ylabel("kg")
    plt.tight_layout()
    plt.savefig(output / "daily_waste.png")
    plt.close()
    requests = frames["collection_requests"].dropna(subset=["assigned_at", "collected_at"]).copy()
    requests["collection_hours"] = (requests["collected_at"] - requests["assigned_at"]).dt.total_seconds() / 3600
    requests[["collection_hours"]].describe(percentiles=[.5, .95]).to_csv(output / "collection_duration_summary.csv")
    complaints = frames["complaints"].dropna(subset=["created_at", "resolved_at"]).copy()
    complaints["resolution_hours"] = (complaints["resolved_at"] - complaints["created_at"]).dt.total_seconds() / 3600
    complaints[["resolution_hours"]].describe(percentiles=[.5, .95]).to_csv(output / "complaint_resolution_summary.csv")
    return ["## 5. Time Analysis", "", "- Daily and monthly waste summaries and charts were generated.", f"- Collection durations available for {len(requests):,} records.", f"- Complaint resolution durations available for {len(complaints):,} records."]


def save_geographical_analysis(frames: dict[str, pd.DataFrame], output: Path) -> list[str]:
    hotspots = ward_performance(frames).sort_values(
        "total_waste_kg", ascending=False
    )
    hotspots.to_csv(output / "geographical_hotspots.csv")
    fig, ax = plt.subplots(figsize=(8, 6))
    plotted = frames["waste_reports"].dropna(
        subset=["latitude", "longitude", "quantity_kg"]
    )
    scatter = ax.scatter(
        plotted["longitude"], plotted["latitude"],
        s=12 + plotted["quantity_kg"].clip(upper=50) * 1.5,
        c=plotted["quantity_kg"], cmap="YlOrRd", alpha=.65,
    )
    ax.set_title("Reported waste locations; marker size/color = reported kg")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    fig.colorbar(scatter, label="Reported kg")
    plt.tight_layout()
    plt.savefig(output / "reported_waste_locations.png")
    plt.close()
    return ["## 6. Geographical Analysis", "", "- Ward hotspot metrics and report-coordinate plot generated from observed report points; no null area centroids are plotted.", "- Vehicle movement should be visualized as timestamp-ordered GPS lines; route distance is unavailable without road/network data."]


def save_citizen_ward_distribution(
    frames: dict[str, pd.DataFrame],
    output: Path,
) -> list[str]:
    distribution = (
        frames["development_seed_citizen_wards"]
        .groupby("ward_id", as_index=False)
        .agg(citizen_count=("citizen_id", "nunique"))
        .merge(
            frames["municipal_wards"][
                ["ward_id", "ward_number", "ward_name", "population"]
            ],
            on="ward_id",
            how="right",
            validate="one_to_one",
        )
    )
    distribution["citizen_count"] = (
        distribution["citizen_count"].fillna(0).astype("int64")
    )
    distribution = distribution[
        ["ward_id", "ward_number", "ward_name", "population", "citizen_count"]
    ].sort_values("ward_id")
    distribution.to_csv(output / "citizen_home_ward_distribution.csv", index=False)
    return [
        "## Citizen Home-Ward Distribution",
        "",
        f"- Per-ward citizen counts are available for all {len(distribution):,} municipal wards in `citizen_home_ward_distribution.csv`.",
        "- Ward population is unchanged; Ward 44 remains NULL. The mapping is a development-data allocation, not an official address record.",
    ]


def business_insights(frames: dict[str, pd.DataFrame]) -> list[str]:
    waste = frames["waste_reports"]
    wards = ward_performance(frames)
    type_total = waste.groupby("waste_type")["quantity_kg"].sum().sort_values(ascending=False)
    requests = frames["collection_requests"]
    workload = requests.assign(
        collected=requests["status"].eq("COLLECTED")
    ).groupby("worker_id")["collected"].agg(["count", "mean"])
    observed = wards.dropna(subset=["collection_efficiency_pct"])
    segregation = wards.dropna(subset=["good_segregation_rate_pct"])
    top_waste = wards.sort_values("total_waste_kg", ascending=False).iloc[0]
    top_complaints = wards.sort_values("complaint_count", ascending=False).iloc[0]
    high_workers = workload.loc[workload["count"] >= workload["count"].median()]
    return [
        "## 7. Business Insights", "",
        f"- Highest-waste ward: Ward {top_waste['ward_number']} ({top_waste['ward_name']}) with {top_waste['total_waste_kg']:,.2f} kg from {int(top_waste['report_count']):,} reports.",
        f"- Highest-waste type: {type_total.index[0]} with {type_total.iloc[0]:,.2f} kg.",
        f"- Highest-complaint ward: Ward {top_complaints['ward_number']} with {int(top_complaints['complaint_count']):,} complaints.",
        *([f"- Collection efficiency ranges from {observed['collection_efficiency_pct'].min():.2f}% to {observed['collection_efficiency_pct'].max():.2f}% across {len(observed)} wards with requests."] if not observed.empty else ["- No collection requests are available to calculate ward collection efficiency."]),
        *([f"- Good segregation rates (ratings 4-5) range from {segregation['good_segregation_rate_pct'].min():.2f}% to {segregation['good_segregation_rate_pct'].max():.2f}% across {len(segregation)} wards with ratings."] if not segregation.empty else ["- No segregation ratings are available to calculate observed segregation rates."]),
        *([f"- Worker collection completion ranges from {high_workers['mean'].min() * 100:.2f}% to {high_workers['mean'].max() * 100:.2f}% among workers at or above median request workload ({workload['count'].median():.0f} requests)."] if not high_workers.empty else ["- No worker has enough assigned workload for a workload-adjusted efficiency comparison."]),
        "- Ward metrics are independently aggregated; current source data has no penalty-to-rating reference, so penalty causality cannot be established.",
    ]


def conclusions(frames: dict[str, pd.DataFrame], quality: pd.DataFrame) -> list[str]:
    issue_total = int(quality["count"].sum()) if not quality.empty else 0
    quality_findings = (
        f"{len(quality):,} issue categories / {issue_total:,} row findings"
        if not quality.empty
        else "no detected data-quality issues"
    )
    return [
        "## 8. EDA Conclusions", "",
        f"- The operational extract contains {len(frames['municipal_wards']):,} municipal wards and {len(frames['waste_reports']):,} waste reports; all results describe this development dataset.",
        f"- EDA identified {quality_findings}; review the issue-level CSV and distinguish intentional nullable fields from invalid missing data before remediation.",
        "- Expose reported waste, collection backlog, complaint concentration, and observed segregation results in Power BI.",
        "- Do not remove high quantities or long durations automatically; classify and audit them first.",
        "- Add penalty-to-rating and complaint-resolver references before causal or worker-accountability analysis.",
        "- The 0.45 kg/person/day baseline is a development assumption only; population NULLs remain NULL and the baseline is not a measured waste total.",
        "- Add weather and road-network data before predictive demand or route-optimization claims.",
    ]


def run_eda(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = load_tables()
    for table, frame in frames.items():
        frame.to_csv(output_dir / f"{table}.csv", index=False)

    overview = database_overview(frames)
    quality_lines, quality_frame = quality_analysis(frames)
    quality_frame.to_csv(output_dir / "data_quality_issues.csv", index=False)
    ward_frame = ward_performance(frames)
    ward_frame.to_csv(output_dir / "ward_performance.csv", index=False)
    sections = [
        "# Smart Waste Management EDA Report", "", f"Generated: {pd.Timestamp.now()}", "",
        *overview,
        *quality_lines,
        *save_univariate(frames, output_dir),
        *save_bivariate(frames, output_dir),
        "## Ward Performance",
        "",
        f"Ward-level report, waste, collection, rating, complaint, and development-baseline metrics are available for {len(ward_frame):,} wards in `ward_performance.csv`.",
        *save_time_analysis(frames, output_dir),
        *save_geographical_analysis(frames, output_dir),
        *save_citizen_ward_distribution(frames, output_dir),
        *business_insights(frames),
        *conclusions(frames, quality_frame),
    ]
    report_path = output_dir / "eda_report.md"
    report_path.write_text("\n".join(sections), encoding="utf-8")
    return report_path


def main():
    parser = argparse.ArgumentParser(description="Run read-only Smart Waste Management EDA")
    parser.add_argument("--output-dir", default="eda_output", help="Directory for report, CSV summaries, and charts")
    args = parser.parse_args()
    report_path = run_eda(Path(args.output_dir))
    print(f"EDA complete: {report_path}")


if __name__ == "__main__":
    main()
