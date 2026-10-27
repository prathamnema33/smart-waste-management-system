"""Extract operational tables from PostgreSQL without modifying the source."""

import logging
from pathlib import Path
from typing import Dict

import argparse
import pandas as pd
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import Engine

import sys

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

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

REQUIRED_COLUMNS = {
    "users": {"user_id", "email", "role"},
    "municipal_wards": {
        "ward_id",
        "ward_number",
        "ward_name",
        "population",
        "boundary_geojson",
    },
    "development_seed_citizen_wards": {
        "seed_name",
        "citizen_id",
        "ward_id",
    },
    "areas": {"area_id", "area_name", "ward_id", "boundary_geojson"},
    "waste_reports": {"report_id", "citizen_id", "area_id", "quantity_kg", "reported_at"},
    "workers": {"worker_id", "user_id", "assigned_area"},
    "collection_requests": {"request_id", "report_id", "worker_id", "assigned_at", "collected_at"},
    "segregation_ratings": {"rating_id", "request_id", "citizen_id", "worker_id", "rating", "rated_at"},
    "reward_transactions": {"transaction_id", "citizen_id", "points", "reference_id", "created_at"},
    "penalties": {"penalty_id", "citizen_id", "amount", "created_at"},
    "complaints": {"complaint_id", "citizen_id", "area_id", "category", "created_at", "resolved_at"},
    "vehicles": {"vehicle_id", "worker_id", "vehicle_number"},
    "vehicle_locations": {"location_id", "vehicle_id", "latitude", "longitude", "recorded_at"},
    "alerts": {"alert_id", "area_id", "alert_type", "created_at"},
}

LOGGER = logging.getLogger("smart_waste_extract")


def extract_table(
    table_name: str,
    raw_dir: Path | None = None,
    source_engine: Engine = engine,
) -> pd.DataFrame:
    """Extract one operational table and save its untouched CSV snapshot."""
    if table_name not in TABLES:
        raise ValueError(
            f"Unsupported table '{table_name}'. Expected one of: {TABLES}"
        )

    output_dir = raw_dir or BACKEND_DIR / "data" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        inspector = inspect(source_engine)
        available = set(inspector.get_table_names(schema="public"))
        if table_name not in available:
            raise RuntimeError(
                f"Required source table does not exist: {table_name}"
            )

        columns = {
            column["name"]
            for column in inspector.get_columns(table_name, schema="public")
        }
        missing_columns = sorted(REQUIRED_COLUMNS[table_name] - columns)
        if missing_columns:
            raise RuntimeError(
                f"{table_name} is missing required columns: {missing_columns}"
            )

        with source_engine.connect() as connection:
            frame = pd.read_sql_query(
                text(f'SELECT * FROM "{table_name}"'),
                connection,
            )
    except SQLAlchemyError as error:
        raise RuntimeError(
            f"Unable to connect to or read table '{table_name}': {error}"
        ) from error

    output_file = output_dir / f"{table_name}.csv"
    frame.to_csv(output_file, index=False)
    LOGGER.info(
        "Extracted table=%s rows=%d columns=%d output=%s",
        table_name,
        len(frame),
        len(frame.columns),
        output_file,
    )
    return frame


def extract_tables(
    source_engine: Engine = engine,
    raw_dir: Path | None = None,
) -> Dict[str, pd.DataFrame]:
    """Extract all required operational tables into ``data/raw``."""
    output_dir = raw_dir or BACKEND_DIR / "data" / "raw"
    LOGGER.info("Extraction started")
    frames: Dict[str, pd.DataFrame] = {}
    for table in TABLES:
        frames[table] = extract_table(table, output_dir, source_engine)
    LOGGER.info("Extraction completed: %d tables", len(frames))
    return frames


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract Smart Waste operational tables to CSV"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=BACKEND_DIR / "data" / "raw",
        help="Directory for extracted CSV files",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    extract_tables(engine, args.output_dir)


if __name__ == "__main__":
    main()
