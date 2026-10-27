"""Data-quality and referential-integrity validation for cleaned frames."""

from typing import Dict, List

import pandas as pd
from shapely.geometry import Point, shape
import json


RELATIONSHIPS = [
    ("areas", "ward_id", "municipal_wards", "ward_id"),
    ("development_seed_citizen_wards", "citizen_id", "users", "user_id"),
    ("development_seed_citizen_wards", "ward_id", "municipal_wards", "ward_id"),
    ("waste_reports", "area_id", "areas", "area_id"),
    ("waste_reports", "citizen_id", "users", "user_id"),
    ("workers", "assigned_area", "areas", "area_id"),
    ("workers", "user_id", "users", "user_id"),
    ("collection_requests", "report_id", "waste_reports", "report_id"),
    ("collection_requests", "worker_id", "workers", "worker_id"),
    ("segregation_ratings", "request_id", "collection_requests", "request_id"),
    ("segregation_ratings", "citizen_id", "users", "user_id"),
    ("segregation_ratings", "worker_id", "workers", "worker_id"),
    ("reward_transactions", "citizen_id", "users", "user_id"),
    ("reward_transactions", "reference_id", "segregation_ratings", "rating_id"),
    ("penalties", "citizen_id", "users", "user_id"),
    ("complaints", "area_id", "areas", "area_id"),
    ("complaints", "citizen_id", "users", "user_id"),
    ("vehicles", "worker_id", "workers", "worker_id"),
    ("vehicle_locations", "vehicle_id", "vehicles", "vehicle_id"),
    ("alerts", "area_id", "areas", "area_id"),
]


def _issue(table: str, column: str, issue_type: str, count: int, severity: str, treatment: str, notes: str) -> dict | None:
    if not count:
        return None
    return {"table_name": table, "column_name": column, "issue_type": issue_type, "issue_count": int(count), "severity": severity, "treatment": treatment, "notes": notes}


def validate_tables(frames: Dict[str, pd.DataFrame], existing_quality: List[dict] | None = None) -> List[dict]:
    """Return quality issues without mutating or deleting source rows."""
    issues = list(existing_quality or [])
    for child_table, child_column, parent_table, parent_column in RELATIONSHIPS:
        child = frames[child_table]
        parent_ids = set(frames[parent_table][parent_column].dropna())
        orphan_count = int((child[child_column].notna() & ~child[child_column].isin(parent_ids)).sum())
        issue = _issue(child_table, child_column, "referential_integrity", orphan_count, "critical", "quarantine", f"No matching {parent_table}.{parent_column}.")
        if issue:
            issues.append(issue)

    duplicate_keys = {
        "waste_reports": ["citizen_id", "area_id", "waste_type", "quantity_kg", "reported_at"],
        "collection_requests": ["report_id", "worker_id", "assigned_at"],
        "segregation_ratings": ["request_id"],
        "reward_transactions": ["citizen_id", "points", "transaction_type", "reference_id", "created_at"],
        "penalties": ["citizen_id", "reason", "amount", "created_at"],
        "complaints": ["citizen_id", "area_id", "category", "description", "created_at"],
        "vehicle_locations": ["vehicle_id", "latitude", "longitude", "recorded_at"],
    }
    for table, keys in duplicate_keys.items():
        duplicates = int(frames[table].duplicated(subset=keys, keep=False).sum())
        issue = _issue(table, ",".join(keys), "duplicate_business_key", duplicates, "medium", "review/quarantine", "Do not silently drop duplicate source records.")
        if issue:
            issues.append(issue)

    unique_keys = {
        "users": ["email"],
        "municipal_wards": ["ward_id", "ward_number"],
        "development_seed_citizen_wards": ["citizen_id"],
        "workers": ["user_id"],
        "vehicles": ["vehicle_number"],
    }
    for table, keys in unique_keys.items():
        for key in keys:
            duplicates = int(frames[table][key].duplicated(keep=False).sum())
            issue = _issue(
                table,
                key,
                "duplicate_unique_key",
                duplicates,
                "critical",
                "review/quarantine",
                "Unique identifiers must not be duplicated.",
            )
            if issue:
                issues.append(issue)

    date_checks = [
        ("collection_requests", "assigned_at/collected_at", (frames["collection_requests"]["collected_at"] < frames["collection_requests"]["assigned_at"]).fillna(False), "collected_at precedes assigned_at"),
        ("complaints", "created_at/resolved_at", (frames["complaints"]["resolved_at"] < frames["complaints"]["created_at"]).fillna(False), "resolved_at precedes created_at"),
    ]
    for table, column, mask, notes in date_checks:
        issue = _issue(table, column, "invalid_date_order", int(mask.sum()), "high", "quarantine", notes)
        if issue:
            issues.append(issue)

    reports = frames["waste_reports"]
    report_dates = reports.set_index("report_id")["reported_at"]
    requests = frames["collection_requests"]
    assigned_before_report = (
        requests["report_id"].map(report_dates).notna()
        & requests["assigned_at"].notna()
        & (
            requests["assigned_at"]
            < requests["report_id"].map(report_dates)
        )
    )
    issue = _issue(
        "collection_requests",
        "assigned_at",
        "collection_before_waste_report",
        int(assigned_before_report.sum()),
        "critical",
        "quarantine",
        "Collection assignment must not precede its waste report.",
    )
    if issue:
        issues.append(issue)

    report_area = reports.set_index("report_id")["area_id"]
    worker_area = frames["workers"].set_index("worker_id")["assigned_area"]
    request_areas = requests["report_id"].map(report_area)
    assigned_areas = requests["worker_id"].map(worker_area)
    area_mismatch = (
        request_areas.notna()
        & assigned_areas.notna()
        & request_areas.ne(assigned_areas)
    )
    issue = _issue(
        "collection_requests",
        "worker_id/area_id",
        "worker_area_mismatch",
        int(area_mismatch.sum()),
        "critical",
        "quarantine",
        "Worker must be assigned to the report's operational area.",
    )
    if issue:
        issues.append(issue)

    collected_request_ids = set(
        requests.loc[requests["status"].eq("COLLECTED"), "request_id"].dropna()
    )
    ratings = frames["segregation_ratings"]
    rating_without_collection = ~ratings["request_id"].isin(collected_request_ids)
    issue = _issue(
        "segregation_ratings",
        "request_id",
        "rating_without_completed_collection",
        int(rating_without_collection.sum()),
        "critical",
        "quarantine",
        "Ratings require a completed collection request.",
    )
    if issue:
        issues.append(issue)

    request_report = requests.set_index("request_id")["report_id"]
    rating_report = ratings["request_id"].map(request_report)
    citizen_by_report = reports.set_index("report_id")["citizen_id"]
    expected_citizen = rating_report.map(citizen_by_report)
    expected_worker = ratings["request_id"].map(requests.set_index("request_id")["worker_id"])
    rating_party_mismatch = (
        ratings["citizen_id"].ne(expected_citizen)
        | ratings["worker_id"].ne(expected_worker)
    ).fillna(False)
    issue = _issue(
        "segregation_ratings",
        "citizen_id/worker_id",
        "rating_party_mismatch",
        int(rating_party_mismatch.sum()),
        "critical",
        "quarantine",
        "Rating citizen and worker must match the report and collection request.",
    )
    if issue:
        issues.append(issue)

    collected_without_time = requests["status"].eq("COLLECTED") & requests["collected_at"].isna()
    issue = _issue(
        "collection_requests",
        "collected_at",
        "collected_request_missing_timestamp",
        int(collected_without_time.sum()),
        "high",
        "quarantine",
        "Collected requests require a collection timestamp.",
    )
    if issue:
        issues.append(issue)

    ward_geometries = {}
    for ward in frames["municipal_wards"].itertuples(index=False):
        try:
            geometry = shape(json.loads(ward.boundary_geojson))
            if not geometry.is_empty and geometry.is_valid:
                ward_geometries[ward.ward_id] = geometry
        except (TypeError, ValueError, json.JSONDecodeError):
            ward_geometries[ward.ward_id] = None

    areas = frames["areas"].set_index("area_id")
    ward_by_area = areas["ward_id"]
    area_geometries = {}
    for area_id, area in areas.iterrows():
        boundary = area.get("boundary_geojson")
        ward_id = area.get("ward_id")
        try:
            if pd.notna(boundary):
                area_geometry = shape(json.loads(boundary))
            else:
                area_geometry = ward_geometries.get(ward_id)
            if area_geometry is None or area_geometry.is_empty or not area_geometry.is_valid:
                area_geometries[area_id] = None
            else:
                area_geometries[area_id] = area_geometry
        except (TypeError, ValueError, json.JSONDecodeError):
            area_geometries[area_id] = None
    for table_name, latitude_col, longitude_col in (
        ("waste_reports", "latitude", "longitude"),
        ("vehicle_locations", "latitude", "longitude"),
    ):
        frame = frames[table_name]
        outside = 0
        if table_name == "waste_reports":
            ward_ids = frame["area_id"].map(ward_by_area)
            area_ids = frame["area_id"]
        else:
            vehicle_worker = (
                frames["vehicles"]
                .set_index("vehicle_id")["worker_id"]
                .map(frames["workers"].set_index("worker_id")["assigned_area"])
            )
            area_by_vehicle = vehicle_worker
            ward_ids = frame["vehicle_id"].map(area_by_vehicle).map(ward_by_area)
            area_ids = frame["vehicle_id"].map(area_by_vehicle)
        for latitude, longitude, ward_id, area_id in zip(
            frame[latitude_col],
            frame[longitude_col],
            ward_ids,
            area_ids,
        ):
            geometry = ward_geometries.get(ward_id)
            area_geometry = area_geometries.get(area_id)
            if (
                geometry is None
                or area_geometry is None
                or pd.isna(latitude)
                or pd.isna(longitude)
                or not area_geometry.covers(Point(float(longitude), float(latitude)))
                or not geometry.covers(Point(float(longitude), float(latitude)))
            ):
                outside += 1
        issue = _issue(
            table_name,
            f"{latitude_col}/{longitude_col}",
            "point_outside_ward_geometry",
            outside,
            "critical",
            "quarantine",
            "Point must be covered by both the associated operational area and municipal ward polygon.",
        )
        if issue:
            issues.append(issue)

    if len(requests) > len(reports):
        issue = _issue(
            "collection_requests",
            "report_id",
            "collection_coverage_exceeds_reports",
            len(requests) - len(reports),
            "high",
            "review",
            "Requests cannot exceed the number of source reports.",
        )
        if issue:
            issues.append(issue)
    if len(ratings) > int(requests["status"].eq("COLLECTED").sum()):
        issue = _issue(
            "segregation_ratings",
            "request_id",
            "ratings_exceed_collected_requests",
            len(ratings) - int(requests["status"].eq("COLLECTED").sum()),
            "high",
            "review",
            "Ratings cannot exceed completed collection requests.",
        )
        if issue:
            issues.append(issue)

    quantity = frames["waste_reports"]["quantity_kg"]
    q1, q3 = quantity.quantile([.25, .75])
    iqr_mask = (quantity < q1 - 1.5 * (q3 - q1)) | (quantity > q3 + 1.5 * (q3 - q1))
    issue = _issue("waste_reports", "quantity_kg", "suspicious_iqr_outlier", int(iqr_mask.sum()), "low", "flag/review", "Do not automatically remove operational extremes.")
    if issue:
        issues.append(issue)

    return issues


def validation_summary(
    frames: Dict[str, pd.DataFrame],
    issues: List[dict],
    cleaned_frames: Dict[str, pd.DataFrame] | None = None,
) -> dict:
    source_rows = int(sum(len(frame) for frame in frames.values()))
    clean_rows = (
        int(sum(len(frame) for frame in cleaned_frames.values()))
        if cleaned_frames is not None
        else source_rows
    )
    return {
        "source_rows": source_rows,
        "clean_rows": clean_rows,
        "quarantined_rows": source_rows - clean_rows,
        "quality_issue_instances": int(sum(issue["issue_count"] for issue in issues)),
        "duplicate_records": int(sum(issue["issue_count"] for issue in issues if "duplicate" in issue["issue_type"])),
        "invalid_records": int(sum(issue["issue_count"] for issue in issues if "invalid" in issue["issue_type"])),
        "missing_value_issues": int(sum(issue["issue_count"] for issue in issues if "missing" in issue["issue_type"])),
        "categorical_issues": int(sum(issue["issue_count"] for issue in issues if "categor" in issue["issue_type"])),
        "date_issues": int(sum(issue["issue_count"] for issue in issues if "date" in issue["issue_type"])),
        "numeric_issues": int(sum(issue["issue_count"] for issue in issues if "numeric" in issue["issue_type"] or "outlier" in issue["issue_type"])),
        "referential_integrity_issues": int(sum(issue["issue_count"] for issue in issues if issue["issue_type"] == "referential_integrity")),
    }
