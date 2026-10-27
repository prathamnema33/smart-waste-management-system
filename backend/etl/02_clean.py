"""Clean extracted Smart Waste CSVs without modifying PostgreSQL or raw files.

Run from the backend directory:
    python etl/02_clean.py

The stage reads only data/raw/, writes normalized tables to data/processed/,
and quarantines invalid records under data/quality/quarantine/.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd


LOGGER = logging.getLogger("smart_waste_clean")
BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = BACKEND_DIR / "data" / "raw"
DEFAULT_PROCESSED_DIR = BACKEND_DIR / "data" / "processed"
DEFAULT_QUALITY_DIR = BACKEND_DIR / "data" / "quality"
DEFAULT_QUARANTINE_DIR = DEFAULT_QUALITY_DIR / "quarantine"

TABLES = [
    "users", "municipal_wards", "development_seed_citizen_wards", "areas", "waste_reports", "workers", "collection_requests",
    "segregation_ratings", "reward_transactions", "penalties", "complaints",
    "vehicles", "vehicle_locations", "alerts",
]

WASTE_TYPE_MAP = {
    "organic": "Organic", "plastic": "Plastic", "paper": "Paper",
    "metal": "Metal", "glass": "Glass", "e waste": "E-Waste",
    "e_waste": "E-Waste", "e-waste": "E-Waste", "mixed": "Mixed",
    "other": "Other",
}
CATEGORY_MAP = {
    "missed collection": "MISSED_COLLECTION", "missed_collection": "MISSED_COLLECTION",
    "illegal dumping": "ILLEGAL_DUMPING", "illegal_dumping": "ILLEGAL_DUMPING",
    "overflowing bin": "OVERFLOWING_BIN", "overflowing_bin": "OVERFLOWING_BIN",
    "segregation": "SEGREGATION",
    "worker issue": "WORKER_ISSUE", "worker_issue": "WORKER_ISSUE", "other": "OTHER",
}
ALLOWED = {
    "users.role": {"CITIZEN", "WORKER", "MONITOR"},
    "waste_reports.priority": {"LOW", "NORMAL", "HIGH", "URGENT"},
    "waste_reports.status": {"PENDING", "ASSIGNED", "COLLECTED"},
    "collection_requests.status": {"ASSIGNED", "IN_PROGRESS", "COLLECTED"},
    "complaints.priority": {"LOW", "NORMAL", "HIGH", "URGENT"},
    "complaints.status": {"OPEN", "IN_PROGRESS", "RESOLVED"},
    "penalties.status": {"PENDING", "PAID"},
    "vehicles.status": {"ACTIVE", "INACTIVE", "MAINTENANCE"},
    "alerts.alert_type": {"HIGH_WASTE", "PENDING_COLLECTION", "REPEATED_COMPLAINTS", "VEHICLE_INACTIVE", "POOR_SEGREGATION", "ILLEGAL_DUMPING", "UNASSIGNED_COLLECTION_DEMAND"},
    "alerts.severity": {"LOW", "MEDIUM", "HIGH", "CRITICAL"},
    "alerts.status": {"OPEN", "RESOLVED"},
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
REQUIRED_DATE_COLUMNS = {
    ("waste_reports", "reported_at"),
    ("collection_requests", "assigned_at"),
    ("complaints", "created_at"),
    ("vehicle_locations", "recorded_at"),
    ("alerts", "created_at"),
}
BUSINESS_KEYS = {
    "municipal_wards": ["ward_number"],
    "development_seed_citizen_wards": ["seed_name", "citizen_id"],
    "waste_reports": ["citizen_id", "area_id", "waste_type", "quantity_kg", "reported_at"],
    "collection_requests": ["report_id", "worker_id", "assigned_at"],
    "segregation_ratings": ["request_id"],
    "reward_transactions": ["citizen_id", "points", "transaction_type", "reference_id", "created_at"],
    "penalties": ["citizen_id", "reason", "amount", "created_at"],
    "complaints": ["citizen_id", "area_id", "category", "description", "created_at"],
    "vehicle_locations": ["vehicle_id", "latitude", "longitude", "recorded_at"],
}
REQUIRED_COLUMNS = {
    "users": ["user_id", "email", "role"],
    "municipal_wards": ["ward_id", "ward_number", "ward_name", "boundary_geojson"],
    "development_seed_citizen_wards": ["seed_name", "citizen_id", "ward_id"],
    "areas": ["area_id", "area_name", "ward_id"],
    "waste_reports": ["report_id", "citizen_id", "area_id", "waste_type", "quantity_kg", "latitude", "longitude", "reported_at"],
    "workers": ["worker_id", "user_id", "assigned_area"],
    "collection_requests": ["request_id", "report_id", "worker_id", "assigned_at"],
    "segregation_ratings": ["rating_id", "request_id", "citizen_id", "worker_id", "rating"],
    "reward_transactions": ["transaction_id", "citizen_id", "points"],
    "penalties": ["penalty_id", "citizen_id", "amount"],
    "complaints": ["complaint_id", "citizen_id", "area_id", "category", "description", "created_at"],
    "vehicles": ["vehicle_id", "vehicle_number", "worker_id"],
    "vehicle_locations": ["location_id", "vehicle_id", "latitude", "longitude", "recorded_at"],
    "alerts": ["alert_id", "area_id", "alert_type", "message", "created_at"],
}
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


def add_issue(issues: list[dict], table: str, column: str, issue_type: str, count: int, severity: str, treatment: str, notes: str) -> None:
    if count:
        issues.append({
            "table_name": table,
            "column_name": column,
            "issue_type": issue_type,
            "issue_count": int(count),
            "severity": severity,
            "treatment": treatment,
            "notes": notes,
        })


def load_raw_tables(raw_dir: Path) -> Dict[str, pd.DataFrame]:
    missing = [table for table in TABLES if not (raw_dir / f"{table}.csv").exists()]
    if missing:
        raise FileNotFoundError(f"Missing extracted CSV files in {raw_dir}: {missing}")
    return {table: pd.read_csv(raw_dir / f"{table}.csv") for table in TABLES}


def _quarantine(quarantine: dict[str, pd.DataFrame], name: str, frame: pd.DataFrame, mask: pd.Series) -> None:
    selected = frame.loc[mask].copy()
    if not selected.empty:
        quarantine[name] = selected


def _clean_text(frame: pd.DataFrame) -> None:
    for column in frame.select_dtypes(include=["object", "string"]).columns:
        frame[column] = frame[column].astype("string").str.strip()


def _normalize_categories(frames: Dict[str, pd.DataFrame], quarantine: dict[str, pd.DataFrame], issues: list[dict]) -> None:
    for table, columns in {
        "users": ["role"], "waste_reports": ["priority", "status"],
        "collection_requests": ["status"], "complaints": ["priority", "status"],
        "penalties": ["status"], "vehicles": ["status"],
        "alerts": ["alert_type", "severity", "status"],
    }.items():
        for column in columns:
            frames[table][column] = frames[table][column].astype("string").str.strip().str.upper()
            allowed = ALLOWED[f"{table}.{column}"]
            invalid = frames[table][column].notna() & ~frames[table][column].isin(allowed)
            add_issue(issues, table, column, "invalid_category", int(invalid.sum()), "high", "quarantine", "Value is outside the database controlled vocabulary.")
            _quarantine(quarantine, f"{table}_{column}_invalid_category", frames[table], invalid)
            frames[table].loc[invalid, "_quarantine"] = True

    waste = frames["waste_reports"]["waste_type"].astype("string").str.strip()
    normalized = waste.str.lower().str.replace(r"[\s-]+", " ", regex=True).map(WASTE_TYPE_MAP)
    frames["waste_reports"]["normalized_waste_type"] = normalized
    invalid = waste.notna() & normalized.isna()
    add_issue(issues, "waste_reports", "waste_type", "invalid_category", int(invalid.sum()), "high", "quarantine", "Unknown waste types are preserved in quarantine.")
    _quarantine(quarantine, "waste_reports_waste_type_invalid_category", frames["waste_reports"], invalid)
    frames["waste_reports"].loc[invalid, "_quarantine"] = True

    category = frames["complaints"]["category"].astype("string").str.strip()
    normalized_category = category.str.lower().str.replace(r"\s+", " ", regex=True).map(CATEGORY_MAP)
    frames["complaints"]["normalized_category"] = normalized_category
    invalid = category.notna() & normalized_category.isna()
    add_issue(issues, "complaints", "category", "invalid_category", int(invalid.sum()), "high", "quarantine", "Unknown complaint categories are preserved in quarantine.")
    _quarantine(quarantine, "complaints_category_invalid_category", frames["complaints"], invalid)
    frames["complaints"].loc[invalid, "_quarantine"] = True


def _convert_dates(frames: Dict[str, pd.DataFrame], quarantine: dict[str, pd.DataFrame], issues: list[dict]) -> None:
    for table, columns in DATE_COLUMNS.items():
        for column in columns:
            source = frames[table][column]
            parsed = pd.to_datetime(source, errors="coerce")
            invalid = source.notna() & parsed.isna()
            add_issue(issues, table, column, "invalid_date", int(invalid.sum()), "high", "quarantine", "Value could not be parsed as a datetime.")
            _quarantine(quarantine, f"{table}_{column}_invalid_date", frames[table], invalid)
            frames[table].loc[invalid, "_quarantine"] = True
            frames[table][column] = parsed


def _validate_numeric(frames: Dict[str, pd.DataFrame], quarantine: dict[str, pd.DataFrame], issues: list[dict]) -> None:
    rules = {
        "waste_reports": [("quantity_kg", lambda value: value <= 0, "quantity_kg must be greater than zero"), ("latitude", lambda value: ~value.between(-90, 90), "latitude must be between -90 and 90"), ("longitude", lambda value: ~value.between(-180, 180), "longitude must be between -180 and 180")],
        "segregation_ratings": [("rating", lambda value: ~value.between(1, 5), "rating must be between 1 and 5")],
        "reward_transactions": [("points", lambda value: value < 0, "reward points cannot be negative")],
        "penalties": [("amount", lambda value: value < 0, "penalty amount cannot be negative")],
        "vehicle_locations": [("latitude", lambda value: ~value.between(-90, 90), "latitude must be between -90 and 90"), ("longitude", lambda value: ~value.between(-180, 180), "longitude must be between -180 and 180")],
    }
    for table, table_rules in rules.items():
        for column, invalid_rule, note in table_rules:
            numeric = pd.to_numeric(frames[table][column], errors="coerce")
            invalid = frames[table][column].notna() & (numeric.isna() | invalid_rule(numeric))
            add_issue(issues, table, column, "invalid_numeric", int(invalid.sum()), "high", "quarantine", note)
            _quarantine(quarantine, f"{table}_{column}_invalid_numeric", frames[table], invalid)
            frames[table].loc[invalid, "_quarantine"] = True
            frames[table][column] = numeric


def _validate_dates(frames: Dict[str, pd.DataFrame], quarantine: dict[str, pd.DataFrame], issues: list[dict]) -> None:
    requests = frames["collection_requests"]
    invalid = requests["assigned_at"].notna() & requests["collected_at"].notna() & (requests["collected_at"] < requests["assigned_at"])
    add_issue(issues, "collection_requests", "assigned_at/collected_at", "invalid_date_order", int(invalid.sum()), "high", "quarantine", "collected_at must be after assigned_at.")
    _quarantine(quarantine, "collection_requests_invalid_date_order", requests, invalid)
    requests.loc[invalid, "_quarantine"] = True

    complaints = frames["complaints"]
    invalid = complaints["created_at"].notna() & complaints["resolved_at"].notna() & (complaints["resolved_at"] < complaints["created_at"])
    add_issue(issues, "complaints", "created_at/resolved_at", "invalid_date_order", int(invalid.sum()), "high", "quarantine", "resolved_at must be after created_at.")
    _quarantine(quarantine, "complaints_invalid_date_order", complaints, invalid)
    complaints.loc[invalid, "_quarantine"] = True


def _validate_missing(frames: Dict[str, pd.DataFrame], quarantine: dict[str, pd.DataFrame], issues: list[dict]) -> None:
    optional = {
        ("collection_requests", "collected_at"): "NULL is valid for an uncollected request.",
        ("complaints", "resolved_at"): "NULL is valid for an unresolved complaint.",
        ("segregation_ratings", "remarks"): "Remarks are optional descriptive text.",
    }
    for table, columns in REQUIRED_COLUMNS.items():
        missing = frames[table][columns].isna().any(axis=1)
        add_issue(issues, table, "*", "required_missing_value", int(missing.sum()), "high", "quarantine", "Required fields are missing.")
        _quarantine(quarantine, f"{table}_required_missing", frames[table], missing)
        frames[table].loc[missing, "_quarantine"] = True

    for table, column in REQUIRED_DATE_COLUMNS:
        missing = frames[table][column].isna()
        add_issue(issues, table, column, "required_missing_date", int(missing.sum()), "high", "quarantine", "A timestamp is required for temporal analytics.")
        _quarantine(quarantine, f"{table}_{column}_missing", frames[table], missing)
        frames[table].loc[missing, "_quarantine"] = True

    for table, frame in frames.items():
        for column in frame.columns:
            if column.startswith("_") or (table, column) in optional:
                if (table, column) in optional:
                    add_issue(issues, table, column, "valid_null", int(frame[column].isna().sum()), "low", "preserve", optional[(table, column)])
                continue
            add_issue(issues, table, column, "missing_value", int(frame[column].isna().sum()), "medium", "review", "Review nullable source values before warehouse loading.")


def _validate_duplicates(frames: Dict[str, pd.DataFrame], quarantine: dict[str, pd.DataFrame], issues: list[dict]) -> None:
    for table, keys in BUSINESS_KEYS.items():
        duplicated = frames[table].duplicated(subset=keys, keep="first")
        add_issue(issues, table, ",".join(keys), "duplicate_business_key", int(duplicated.sum()), "medium", "quarantine", "First occurrence retained; duplicate occurrence quarantined.")
        _quarantine(quarantine, f"{table}_duplicate_business_key", frames[table], duplicated)
        frames[table].loc[duplicated, "_quarantine"] = True


def _validate_references(frames: Dict[str, pd.DataFrame], quarantine: dict[str, pd.DataFrame], issues: list[dict]) -> None:
    for child_table, child_column, parent_table, parent_column in RELATIONSHIPS:
        parent_ids = set(frames[parent_table][parent_column].dropna())
        invalid = frames[child_table][child_column].notna() & ~frames[child_table][child_column].isin(parent_ids)
        add_issue(issues, child_table, child_column, "referential_integrity", int(invalid.sum()), "critical", "quarantine", f"No matching {parent_table}.{parent_column}.")
        _quarantine(quarantine, f"{child_table}_{child_column}_orphan", frames[child_table], invalid)
        frames[child_table].loc[invalid, "_quarantine"] = True


def _validate_business_rules(
    frames: Dict[str, pd.DataFrame],
    quarantine: dict[str, pd.DataFrame],
    issues: list[dict],
) -> None:
    reports = frames["waste_reports"]
    requests = frames["collection_requests"]
    report_dates = reports.set_index("report_id")["reported_at"]
    request_report_dates = requests["report_id"].map(report_dates)
    before_report = (
        request_report_dates.notna()
        & requests["assigned_at"].notna()
        & (requests["assigned_at"] < request_report_dates)
    )
    add_issue(
        issues,
        "collection_requests",
        "assigned_at",
        "collection_before_waste_report",
        int(before_report.sum()),
        "high",
        "quarantine",
        "Collection assignment must not precede its waste report.",
    )
    _quarantine(quarantine, "collection_requests_before_report", requests, before_report)
    requests.loc[before_report, "_quarantine"] = True

    report_area = reports.set_index("report_id")["area_id"]
    request_area = requests["report_id"].map(report_area)
    worker_area = frames["workers"].set_index("worker_id")["assigned_area"]
    assigned_area = requests["worker_id"].map(worker_area)
    area_mismatch = request_area.notna() & assigned_area.notna() & request_area.ne(assigned_area)
    add_issue(
        issues,
        "collection_requests",
        "worker_id/area_id",
        "worker_area_mismatch",
        int(area_mismatch.sum()),
        "critical",
        "quarantine",
        "Assigned worker must serve the report's operational area.",
    )
    _quarantine(quarantine, "collection_requests_worker_area_mismatch", requests, area_mismatch)
    requests.loc[area_mismatch, "_quarantine"] = True

    collected_request_ids = set(
        requests.loc[requests["status"].eq("COLLECTED"), "request_id"].dropna()
    )
    ratings = frames["segregation_ratings"]
    rating_without_collection = ~ratings["request_id"].isin(collected_request_ids)
    add_issue(
        issues,
        "segregation_ratings",
        "request_id",
        "rating_without_completed_collection",
        int(rating_without_collection.sum()),
        "critical",
        "quarantine",
        "Segregation ratings require a collected request.",
    )
    _quarantine(
        quarantine,
        "segregation_ratings_without_collection",
        ratings,
        rating_without_collection,
    )
    ratings.loc[rating_without_collection, "_quarantine"] = True

    report_by_request = requests.set_index("request_id")["report_id"]
    rating_report_ids = ratings["request_id"].map(report_by_request)
    citizen_by_report = reports.set_index("report_id")["citizen_id"]
    worker_by_request = requests.set_index("request_id")["worker_id"]
    wrong_citizen = (
        ratings["citizen_id"].notna()
        & rating_report_ids.map(citizen_by_report).notna()
        & ratings["citizen_id"].ne(rating_report_ids.map(citizen_by_report))
    )
    wrong_worker = (
        ratings["worker_id"].notna()
        & ratings["request_id"].map(worker_by_request).notna()
        & ratings["worker_id"].ne(ratings["request_id"].map(worker_by_request))
    )
    for column, invalid in (
        ("citizen_id", wrong_citizen),
        ("worker_id", wrong_worker),
    ):
        add_issue(
            issues,
            "segregation_ratings",
            column,
            "rating_party_mismatch",
            int(invalid.sum()),
            "critical",
            "quarantine",
            "Rating citizen and worker must match its report and collection request.",
        )
        _quarantine(
            quarantine,
            f"segregation_ratings_{column}_mismatch",
            ratings,
            invalid,
        )
        ratings.loc[invalid, "_quarantine"] = True

    duplicate_emails = frames["users"]["email"].duplicated(keep="first")
    add_issue(
        issues,
        "users",
        "email",
        "duplicate_user_email",
        int(duplicate_emails.sum()),
        "critical",
        "quarantine",
        "Email must uniquely identify a user.",
    )
    _quarantine(quarantine, "users_duplicate_email", frames["users"], duplicate_emails)
    frames["users"].loc[duplicate_emails, "_quarantine"] = True

    duplicate_worker_users = frames["workers"]["user_id"].duplicated(keep="first")
    add_issue(
        issues,
        "workers",
        "user_id",
        "duplicate_worker_user",
        int(duplicate_worker_users.sum()),
        "high",
        "quarantine",
        "A user may have only one worker record.",
    )
    _quarantine(
        quarantine,
        "workers_duplicate_user",
        frames["workers"],
        duplicate_worker_users,
    )
    frames["workers"].loc[duplicate_worker_users, "_quarantine"] = True

    penalties = frames["penalties"]
    add_issue(
        issues,
        "penalties",
        "reference",
        "source_rating_not_traceable",
        len(penalties),
        "low",
        "document limitation",
        "The source schema has no rating/reference key on penalties; citizen-level linkage cannot prove rating causality.",
    )


def clean_tables(frames: Dict[str, pd.DataFrame]) -> Tuple[Dict[str, pd.DataFrame], Dict[str, pd.DataFrame], List[dict]]:
    """Clean frames and return processed candidates, quarantine frames, and issues."""
    cleaned = {table: frame.copy() for table, frame in frames.items()}
    quarantine: dict[str, pd.DataFrame] = {}
    issues: list[dict] = []
    for frame in cleaned.values():
        frame["_quarantine"] = False
        _clean_text(frame)
    _normalize_categories(cleaned, quarantine, issues)
    _convert_dates(cleaned, quarantine, issues)
    _validate_numeric(cleaned, quarantine, issues)
    _validate_dates(cleaned, quarantine, issues)
    _validate_missing(cleaned, quarantine, issues)
    _validate_duplicates(cleaned, quarantine, issues)
    _validate_references(cleaned, quarantine, issues)
    _validate_business_rules(cleaned, quarantine, issues)
    processed = {}
    for table, frame in cleaned.items():
        processed[table] = frame.loc[~frame["_quarantine"]].drop(
            columns=["_quarantine"]
        ).copy()
    for frame in quarantine.values():
        if "_quarantine" in frame.columns:
            frame.drop(columns=["_quarantine"], inplace=True)
    return processed, quarantine, issues


def write_outputs(cleaned: Dict[str, pd.DataFrame], quarantine: Dict[str, pd.DataFrame], issues: List[dict], raw_frames: Dict[str, pd.DataFrame], processed_dir: Path, quality_dir: Path) -> pd.DataFrame:
    processed_dir.mkdir(parents=True, exist_ok=True)
    quarantine_dir = quality_dir / "quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    for old_file in quarantine_dir.glob("*.csv"):
        old_file.unlink()
    for table, frame in cleaned.items():
        frame.to_csv(processed_dir / f"{table}.csv", index=False)
    for name, frame in quarantine.items():
        frame.to_csv(quarantine_dir / f"{name}.csv", index=False)

    issue_frame = pd.DataFrame(issues)
    summary_rows = []
    for table in TABLES:
        table_issues = issue_frame.loc[issue_frame["table_name"].eq(table)] if not issue_frame.empty else pd.DataFrame()
        summary_rows.append({
            "table_name": table,
            "source_rows": len(raw_frames[table]),
            "clean_rows": len(cleaned[table]),
            "quarantined_rows": len(raw_frames[table]) - len(cleaned[table]),
            "missing_value_issues": int(table_issues.loc[table_issues["issue_type"].isin(["missing_value", "required_missing_value", "required_missing_date", "valid_null"]), "issue_count"].sum()) if not table_issues.empty else 0,
            "categorical_issues": int(table_issues.loc[table_issues["issue_type"].eq("invalid_category"), "issue_count"].sum()) if not table_issues.empty else 0,
            "numeric_issues": int(table_issues.loc[table_issues["issue_type"].eq("invalid_numeric"), "issue_count"].sum()) if not table_issues.empty else 0,
            "date_issues": int(table_issues.loc[table_issues["issue_type"].isin(["invalid_date", "invalid_date_order"]), "issue_count"].sum()) if not table_issues.empty else 0,
            "duplicate_issues": int(table_issues.loc[table_issues["issue_type"].eq("duplicate_business_key"), "issue_count"].sum()) if not table_issues.empty else 0,
            "notes": "; ".join(sorted(table_issues["notes"].dropna().unique())) if not table_issues.empty else "No issues detected.",
        })
    summary = pd.DataFrame(summary_rows)
    quality_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(quality_dir / "cleaning_summary.csv", index=False)
    if not issue_frame.empty:
        issue_frame.to_csv(quality_dir / "cleaning_issues_detail.csv", index=False)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean extracted Smart Waste CSV files")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    parser.add_argument("--quality-dir", type=Path, default=DEFAULT_QUALITY_DIR)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    LOGGER.info("Cleaning started; source=%s", args.raw_dir)
    raw_frames = load_raw_tables(args.raw_dir)
    cleaned, quarantine, issues = clean_tables(raw_frames)
    summary = write_outputs(cleaned, quarantine, issues, raw_frames, args.processed_dir, args.quality_dir)
    LOGGER.info("Cleaning completed; quarantine datasets=%d", len(quarantine))
    print("====================================")
    print("SMART WASTE CLEANING SUMMARY")
    print("====================================")
    print(f"Source rows: {int(summary['source_rows'].sum()):,}")
    print(f"Clean rows: {int(summary['clean_rows'].sum()):,}")
    print(f"Quarantined rows: {int(summary['quarantined_rows'].sum()):,}")
    print(f"Quality issues: {len(issues):,}")
    print(f"Processed output: {args.processed_dir}")
    print(f"Quarantine output: {args.quality_dir / 'quarantine'}")
    print(f"Summary: {args.quality_dir / 'cleaning_summary.csv'}")


if __name__ == "__main__":
    main()
