"""Run the read-only Smart Waste Management ETL pipeline."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd

LOGGER = logging.getLogger("smart_waste_etl")
BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent
DATA_DIR = BASE_DIR.parent / "data"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import engine


def load_numbered_module(filename: str) -> ModuleType:
    path = BASE_DIR / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load ETL module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_frames(frames: dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False)


def write_quarantine(quarantine: dict[str, pd.DataFrame], output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = 0
    current_files = {f"{name}.csv" for name in quarantine}
    for name, frame in quarantine.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False)
        rows += len(frame)
    for old_file in output_dir.glob("*.csv"):
        if old_file.name not in current_files:
            old_file.unlink()
    return rows


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def run_pipeline(data_dir: Path = DATA_DIR) -> dict:
    extract = load_numbered_module("01_extract.py")
    clean = load_numbered_module("02_clean.py")
    transform = load_numbered_module("03_transform.py")
    validate = load_numbered_module("04_validate.py")

    raw_dir = data_dir / "raw"
    processed_dir = data_dir / "processed"
    analytics_dir = data_dir / "analytics"
    quality_dir = data_dir / "quality"
    quarantine_dir = quality_dir / "quarantine"

    LOGGER.info("Extraction started")
    frames = extract.extract_tables(engine, raw_dir)
    LOGGER.info("Extraction completed: %s source tables, %s rows", len(frames), sum(len(frame) for frame in frames.values()))

    LOGGER.info("Cleaning started")
    cleaned, quarantine, quality = clean.clean_tables(frames)
    write_frames(cleaned, processed_dir)
    LOGGER.info("Cleaning completed: %s quarantine datasets", len(quarantine))

    LOGGER.info("Validation started")
    quality = validate.validate_tables(cleaned, quality)
    quality_frame = pd.DataFrame(quality, columns=[
        "table_name", "column_name", "issue_type", "issue_count", "severity", "treatment", "notes",
    ])
    quality_dir.mkdir(parents=True, exist_ok=True)
    quality_frame.to_csv(quality_dir / "data_quality_report.csv", index=False)
    quarantine_rows = write_quarantine(quarantine, quarantine_dir)
    LOGGER.info("Validation completed: %s quality issue rows", len(quality_frame))

    LOGGER.info("Transformation started")
    transformed = transform.transform_tables(cleaned)
    write_frames(transformed, analytics_dir)
    LOGGER.info("Transformation completed: %s analytics datasets", len(transformed))

    summary = validate.validation_summary(frames, quality, cleaned)
    summary["quarantine_dataset_rows"] = quarantine_rows
    pd.DataFrame([summary]).to_csv(quality_dir / "etl_summary.csv", index=False)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run read-only Smart Waste Management ETL")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help="Output data directory")
    args = parser.parse_args()
    configure_logging()
    try:
        summary = run_pipeline(args.data_dir)
    except Exception:
        LOGGER.exception("ETL failed")
        raise

    print("====================================")
    print("SMART WASTE ETL SUMMARY")
    print("====================================")
    for key, value in summary.items():
        print(f"{key.replace('_', ' ').title()}: {value:,}")
    print(f"Raw output: {args.data_dir / 'raw'}")
    print(f"Processed output: {args.data_dir / 'processed'}")
    print(f"Analytics output: {args.data_dir / 'analytics'}")
    print(f"Quality report: {args.data_dir / 'quality' / 'data_quality_report.csv'}")
    print(f"Quarantine output: {args.data_dir / 'quality' / 'quarantine'}")


if __name__ == "__main__":
    main()
