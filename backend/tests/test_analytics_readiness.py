"""Read-only acceptance tests for the current Bhopal analytics dataset."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

import pandas as pd
from shapely.geometry import Point, shape
from sqlalchemy import text

from database import engine


BACKEND_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BACKEND_DIR / "data" / "raw"
ANALYTICS_DIR = BACKEND_DIR / "data" / "analytics"
QUALITY_DIR = BACKEND_DIR / "data" / "quality"
SEED_NAME = "bhopal-development-v1"
SEED_EMAIL_PREFIX = "seed."
SEED_VEHICLE_PREFIX = "SEED-MP28-"

SOURCE_TABLES = (
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
)

FACT_OUTPUTS = {
    "waste_reports": "fact_waste",
    "collection_requests": "fact_collection",
    "complaints": "fact_complaint",
    "segregation_ratings": "fact_rating",
    "reward_transactions": "fact_reward",
    "penalties": "fact_penalty",
    "vehicle_locations": "fact_gps",
    "alerts": "fact_alert",
}

FOREIGN_KEY_RELATIONSHIPS = (
    ("areas", "ward_id", "municipal_wards", "ward_id"),
    (
        "development_seed_citizen_wards",
        "citizen_id",
        "users",
        "user_id",
    ),
    (
        "development_seed_citizen_wards",
        "ward_id",
        "municipal_wards",
        "ward_id",
    ),
    ("workers", "user_id", "users", "user_id"),
    ("workers", "assigned_area", "areas", "area_id"),
    ("waste_reports", "citizen_id", "users", "user_id"),
    ("waste_reports", "area_id", "areas", "area_id"),
    ("collection_requests", "report_id", "waste_reports", "report_id"),
    ("collection_requests", "worker_id", "workers", "worker_id"),
    ("segregation_ratings", "request_id", "collection_requests", "request_id"),
    ("segregation_ratings", "citizen_id", "users", "user_id"),
    ("segregation_ratings", "worker_id", "workers", "worker_id"),
    ("reward_transactions", "citizen_id", "users", "user_id"),
    (
        "reward_transactions",
        "reference_id",
        "segregation_ratings",
        "rating_id",
    ),
    ("penalties", "citizen_id", "users", "user_id"),
    ("complaints", "citizen_id", "users", "user_id"),
    ("complaints", "area_id", "areas", "area_id"),
    ("vehicles", "worker_id", "workers", "worker_id"),
    ("vehicle_locations", "vehicle_id", "vehicles", "vehicle_id"),
    ("alerts", "area_id", "areas", "area_id"),
    ("teams", "area_id", "areas", "area_id"),
    ("teams", "leader_worker_id", "workers", "worker_id"),
    ("teams", "vehicle_id", "vehicles", "vehicle_id"),
    ("team_members", "team_id", "teams", "team_id"),
    ("team_members", "worker_id", "workers", "worker_id"),
)


class AnalyticsReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.connection = engine.connect()
        cls.transaction = cls.connection.begin()
        cls.connection.execute(text("SET TRANSACTION READ ONLY"))
        cls.frames = {
            table: pd.read_sql_query(text(f'SELECT * FROM "{table}"'), cls.connection)
            for table in SOURCE_TABLES
        }
        cls.raw = {
            table: pd.read_csv(RAW_DIR / f"{table}.csv")
            for table in SOURCE_TABLES
        }
        cls.analytics = {
            name: pd.read_csv(ANALYTICS_DIR / f"{name}.csv")
            for name in (
                "fact_waste",
                "fact_collection",
                "fact_complaint",
                "fact_rating",
                "fact_segmentation",
                "fact_reward",
                "fact_penalty",
                "fact_gps",
                "fact_alert",
                "dim_ward",
                "dim_citizen",
                "analytics_ward_performance",
                "analytics_ward_priority_score",
            )
        }
        cls.manifest = pd.read_sql_query(
            text(
                """
                SELECT table_name, record_id
                FROM development_seed_records
                WHERE seed_name = :seed_name
                """
            ),
            cls.connection,
            params={"seed_name": SEED_NAME},
        )
        cls.quality_summary = pd.read_csv(QUALITY_DIR / "etl_summary.csv").iloc[0]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.transaction.rollback()
        cls.connection.close()

    def check(
        self,
        test_number: int,
        name: str,
        actual: Any,
        expected: Any,
        passed: bool | None = None,
    ) -> None:
        result = actual == expected if passed is None else passed
        status = "PASS" if result else "FAIL"
        print(
            f"[{status}] {test_number:02d}. {name} | "
            f"actual={actual!r} | expected={expected!r}",
            flush=True,
        )
        self.assertTrue(result, f"{name}: actual={actual!r}; expected={expected!r}")

    def scalar(self, query: str, params: dict | None = None) -> int:
        return int(self.connection.execute(text(query), params or {}).scalar_one())

    def orphan_count(self, generated_only: bool = False) -> int:
        total = 0
        for child, child_key, parent, parent_key in FOREIGN_KEY_RELATIONSHIPS:
            where = [
                f"c.{child_key} IS NOT NULL",
                f"NOT EXISTS (SELECT 1 FROM {parent} p WHERE p.{parent_key} = c.{child_key})",
            ]
            if generated_only:
                if child == "development_seed_citizen_wards":
                    where.append(f"c.seed_name = '{SEED_NAME}'")
                    total += self.scalar(
                        f"SELECT COUNT(*) FROM {child} c WHERE {' AND '.join(where)}"
                    )
                    continue
                child_id = {
                    "areas": "area_id",
                    "users": "user_id",
                    "workers": "worker_id",
                    "vehicles": "vehicle_id",
                    "teams": "team_id",
                    "team_members": "worker_id",
                    "waste_reports": "report_id",
                    "collection_requests": "request_id",
                    "segregation_ratings": "rating_id",
                    "reward_transactions": "transaction_id",
                    "penalties": "penalty_id",
                    "complaints": "complaint_id",
                    "vehicle_locations": "location_id",
                    "alerts": "alert_id",
                }[child]
                where.append(
                    "EXISTS (SELECT 1 FROM development_seed_records sr "
                    f"WHERE sr.seed_name = '{SEED_NAME}' "
                    f"AND sr.table_name = '{child}' "
                    f"AND sr.record_id = c.{child_id})"
                )
            total += self.scalar(
                f"SELECT COUNT(*) FROM {child} c WHERE {' AND '.join(where)}"
            )
        return total

    def test_01_record_count_expectations(self) -> None:
        actual = {
            "wards": len(self.frames["municipal_wards"]),
            "citizens": int(self.frames["users"]["role"].eq("CITIZEN").sum()),
            "workers": len(self.frames["workers"]),
            "reports": len(self.frames["waste_reports"]),
        }
        expected = {"wards": 85, "citizens": 1000, "workers": 50, "reports": 2000}
        self.check(1, "Record-count expectations", actual, expected)

    def test_02_foreign_key_integrity(self) -> None:
        actual = self.orphan_count()
        self.check(2, "Foreign-key integrity (orphan reference edges)", actual, 0)

    def test_03_orphan_records(self) -> None:
        actual = self.orphan_count(generated_only=True)
        self.check(3, "Generated orphan records", actual, 0)

    def test_04_duplicate_generated_records(self) -> None:
        duplicate_emails = self.scalar(
            """
            SELECT COUNT(*) FROM (
                SELECT email FROM users
                WHERE email LIKE :prefix
                GROUP BY email HAVING COUNT(*) > 1
            ) duplicates
            """,
            {"prefix": f"{SEED_EMAIL_PREFIX}%"},
        )
        duplicate_vehicles = self.scalar(
            """
            SELECT COUNT(*) FROM (
                SELECT vehicle_number FROM vehicles
                WHERE vehicle_number LIKE :prefix
                GROUP BY vehicle_number HAVING COUNT(*) > 1
            ) duplicates
            """,
            {"prefix": f"{SEED_VEHICLE_PREFIX}%"},
        )
        duplicate_requests = int(
            self.frames["collection_requests"]["report_id"].duplicated().sum()
        )
        duplicate_citizen_mappings = self.scalar(
            """
            SELECT COUNT(*) FROM (
                SELECT citizen_id FROM development_seed_citizen_wards
                WHERE seed_name = :seed_name
                GROUP BY citizen_id HAVING COUNT(*) > 1
            ) duplicates
            """,
            {"seed_name": SEED_NAME},
        )
        actual = {
            "generated_emails": duplicate_emails,
            "generated_vehicle_numbers": duplicate_vehicles,
            "duplicate_report_requests": duplicate_requests,
            "duplicate_citizen_mappings": duplicate_citizen_mappings,
        }
        self.check(4, "Duplicate generated records", actual, {
            "generated_emails": 0,
            "generated_vehicle_numbers": 0,
            "duplicate_report_requests": 0,
            "duplicate_citizen_mappings": 0,
        })

    def test_05_citizen_to_ward_consistency(self) -> None:
        mappings = self.frames["development_seed_citizen_wards"]
        citizens = self.frames["users"].loc[
            self.frames["users"]["role"].eq("CITIZEN"), ["user_id"]
        ]
        invalid_reports = self.scalar(
            """
            SELECT COUNT(*)
            FROM waste_reports r
            JOIN areas a ON a.area_id = r.area_id
            LEFT JOIN development_seed_citizen_wards m
              ON m.citizen_id = r.citizen_id
             AND m.seed_name = :seed_name
            WHERE m.citizen_id IS NULL OR m.ward_id <> a.ward_id
            """,
            {"seed_name": SEED_NAME},
        )
        invalid_complaints = self.scalar(
            """
            SELECT COUNT(*)
            FROM complaints c
            JOIN areas a ON a.area_id = c.area_id
            LEFT JOIN development_seed_citizen_wards m
              ON m.citizen_id = c.citizen_id
             AND m.seed_name = :seed_name
            WHERE m.citizen_id IS NULL OR m.ward_id <> a.ward_id
            """,
            {"seed_name": SEED_NAME},
        )
        actual = {
            "citizens": len(citizens),
            "unique_mappings": mappings["citizen_id"].nunique(),
            "citizen_without_mapping": len(set(citizens.user_id) - set(mappings.citizen_id)),
            "report_ward_mismatches": invalid_reports,
            "complaint_ward_mismatches": invalid_complaints,
        }
        expected = {
            "citizens": 1000,
            "unique_mappings": 1000,
            "citizen_without_mapping": 0,
            "report_ward_mismatches": 0,
            "complaint_ward_mismatches": 0,
        }
        self.check(5, "Citizen-to-ward consistency", actual, expected)

    def test_06_report_area_ward_consistency(self) -> None:
        actual = self.scalar(
            """
            SELECT COUNT(*)
            FROM waste_reports r
            LEFT JOIN areas a ON a.area_id = r.area_id
            LEFT JOIN municipal_wards w ON w.ward_id = a.ward_id
            WHERE a.area_id IS NULL OR w.ward_id IS NULL
               OR a.ward_id <> w.ward_id
            """
        )
        self.check(6, "Report-to-area-to-ward consistency", actual, 0)

    def test_07_worker_area_consistency(self) -> None:
        actual = self.scalar(
            """
            SELECT COUNT(*)
            FROM workers w
            LEFT JOIN areas a ON a.area_id = w.assigned_area
            LEFT JOIN users u ON u.user_id = w.user_id
            WHERE a.area_id IS NULL OR u.role <> 'WORKER'
               OR (SELECT COUNT(*) FROM team_members tm
                   WHERE tm.worker_id = w.worker_id) <> 1
            """
        )
        self.check(7, "Worker-to-area and active-team consistency", actual, 0)

    def test_08_collection_report_consistency(self) -> None:
        actual = self.scalar(
            """
            SELECT COUNT(*)
            FROM collection_requests c
            LEFT JOIN waste_reports r ON r.report_id = c.report_id
            LEFT JOIN workers w ON w.worker_id = c.worker_id
            WHERE r.report_id IS NULL OR w.worker_id IS NULL
               OR r.area_id <> w.assigned_area
               OR (SELECT COUNT(*) FROM collection_requests other
                   WHERE other.report_id = c.report_id) <> 1
            """
        )
        self.check(8, "Collection-to-report and worker-area consistency", actual, 0)

    def test_09_collection_date_order(self) -> None:
        actual = self.scalar(
            """
            SELECT COUNT(*)
            FROM collection_requests c
            JOIN waste_reports r ON r.report_id = c.report_id
            WHERE c.assigned_at < r.reported_at
               OR c.collected_at < r.reported_at
               OR c.collected_at < c.assigned_at
            """
        )
        self.check(9, "Collection assigned date >= report date", actual, 0)

    def test_10_ratings_require_collected_requests(self) -> None:
        actual = self.scalar(
            """
            SELECT COUNT(*)
            FROM segregation_ratings g
            LEFT JOIN collection_requests c ON c.request_id = g.request_id
            LEFT JOIN waste_reports r ON r.report_id = c.report_id
            WHERE c.request_id IS NULL OR c.status <> 'COLLECTED'
               OR g.citizen_id <> r.citizen_id
               OR g.worker_id <> c.worker_id
            """
        )
        self.check(10, "Ratings only for matching collected requests", actual, 0)

    def test_11_reward_and_penalty_references(self) -> None:
        invalid_rewards = self.scalar(
            """
            SELECT COUNT(*)
            FROM reward_transactions reward
            LEFT JOIN segregation_ratings rating
              ON rating.rating_id = reward.reference_id
            WHERE rating.rating_id IS NULL
               OR rating.citizen_id <> reward.citizen_id
            """
        )
        invalid_penalties = self.scalar(
            """
            SELECT COUNT(*)
            FROM penalties penalty
            LEFT JOIN users citizen ON citizen.user_id = penalty.citizen_id
            WHERE citizen.user_id IS NULL OR citizen.role <> 'CITIZEN'
            """
        )
        actual = {"invalid_rewards": invalid_rewards, "invalid_penalties": invalid_penalties}
        self.check(11, "Reward/penalty references", actual, {
            "invalid_rewards": 0,
            "invalid_penalties": 0,
        })

    def test_12_vehicle_gps_integrity(self) -> None:
        actual = {
            "gps_orphans": self.scalar(
                """
                SELECT COUNT(*) FROM vehicle_locations gps
                LEFT JOIN vehicles vehicle ON vehicle.vehicle_id = gps.vehicle_id
                WHERE vehicle.vehicle_id IS NULL
                """
            ),
            "gps_records": len(self.frames["vehicle_locations"]),
            "vehicles": len(self.frames["vehicles"]),
        }
        expected = {"gps_orphans": 0, "gps_records": 2000, "vehicles": 10}
        self.check(12, "Vehicle-GPS integrity", actual, expected)

    def test_13_geographic_boundaries(self) -> None:
        ward_geometries = {
            int(row.ward_id): shape(json.loads(row.boundary_geojson))
            for row in self.frames["municipal_wards"].itertuples(index=False)
        }
        area_geometries = {}
        area_wards = {}
        for area in self.frames["areas"].itertuples(index=False):
            ward_id = int(area.ward_id)
            area_wards[int(area.area_id)] = ward_id
            area_geometries[int(area.area_id)] = (
                shape(json.loads(area.boundary_geojson))
                if pd.notna(area.boundary_geojson) and area.boundary_geojson
                else ward_geometries[ward_id]
            )

        report_misses = 0
        for row in self.frames["waste_reports"].itertuples(index=False):
            point = Point(float(row.longitude), float(row.latitude))
            area_id = int(row.area_id)
            ward_id = area_wards[area_id]
            if not area_geometries[area_id].covers(point) or not ward_geometries[ward_id].covers(point):
                report_misses += 1

        worker_areas = self.frames["workers"].set_index("worker_id")["assigned_area"]
        vehicle_workers = self.frames["vehicles"].set_index("vehicle_id")["worker_id"]
        gps_misses = 0
        for row in self.frames["vehicle_locations"].itertuples(index=False):
            point = Point(float(row.longitude), float(row.latitude))
            area_id = int(worker_areas.loc[vehicle_workers.loc[row.vehicle_id]])
            ward_id = area_wards[area_id]
            if not area_geometries[area_id].covers(point) or not ward_geometries[ward_id].covers(point):
                gps_misses += 1

        actual = {"reports_outside_area_or_ward": report_misses, "gps_outside_area_or_ward": gps_misses}
        self.check(13, "Report/GPS geographic boundary validation", actual, {
            "reports_outside_area_or_ward": 0,
            "gps_outside_area_or_ward": 0,
        })

    def test_14_seeder_idempotency_read_only(self) -> None:
        registered = self.manifest.groupby("table_name")["record_id"].nunique().to_dict()
        generated_citizens = self.scalar(
            "SELECT COUNT(*) FROM users WHERE role='CITIZEN' AND email LIKE 'seed.citizen%'"
        )
        generated_workers = self.scalar(
            "SELECT COUNT(*) FROM workers worker JOIN users user_row "
            "ON user_row.user_id=worker.user_id "
            "WHERE user_row.email LIKE 'seed.worker%'"
        )
        actual = {
            "registered_citizens": generated_citizens,
            "registered_workers": generated_workers,
            "registered_reports": registered.get("waste_reports", 0),
            "registered_users": registered.get("users", 0),
            "registered_workers": registered.get("workers", 0),
            "new_records_required_on_rerun": max(0, 1000 - generated_citizens)
            + max(0, 50 - generated_workers)
            + max(0, 2000 - registered.get("waste_reports", 0)),
        }
        expected = {
            "registered_citizens": 1000,
            "registered_workers": 50,
            "registered_reports": 2000,
            "registered_users": 1050,
            "registered_workers": 50,
            "new_records_required_on_rerun": 0,
        }
        self.check(14, "Seeder idempotency (read-only no-op state)", actual, expected)

    def test_15_etl_source_output_reconciliation(self) -> None:
        source_snapshot = {
            table: {
                "database": len(self.frames[table]),
                "raw_snapshot": len(self.raw[table]),
            }
            for table in SOURCE_TABLES
        }
        fact_snapshot = {
            f"{source}->{output}": {
                "raw_snapshot": len(self.raw[source]),
                "analytics_output": len(self.analytics[output]),
            }
            for source, output in FACT_OUTPUTS.items()
        }
        fact_snapshot["segregation_ratings->fact_segmentation"] = {
            "raw_snapshot": len(self.raw["segregation_ratings"]),
            "analytics_output": len(self.analytics["fact_segmentation"]),
        }
        stale_quarantine_files = sorted(
            path.name for path in (QUALITY_DIR / "quarantine").glob("*.csv")
        )
        passed = all(
            counts["database"] == counts["raw_snapshot"]
            for counts in source_snapshot.values()
        ) and all(
            counts["raw_snapshot"] == counts["analytics_output"]
            for counts in fact_snapshot.values()
        ) and not stale_quarantine_files
        actual = {
            "database_to_raw": source_snapshot,
            "raw_to_analytics": fact_snapshot,
            "stale_quarantine_csvs": stale_quarantine_files,
        }
        expected = {
            "database_to_raw": "all row counts equal",
            "raw_to_analytics": "all row counts equal",
            "stale_quarantine_csvs": [],
        }
        self.check(15, "ETL source-to-output reconciliation", actual, expected, passed)

    def test_16_kpi_reconciliation(self) -> None:
        reports = self.raw["waste_reports"].merge(
            self.raw["areas"][["area_id", "ward_id"]],
            on="area_id",
            how="left",
            validate="many_to_one",
        )
        requests = self.raw["collection_requests"].merge(
            reports[["report_id", "ward_id"]],
            on="report_id",
            how="left",
            validate="many_to_one",
        )
        ratings = self.raw["segregation_ratings"].merge(
            requests[["request_id", "ward_id"]],
            on="request_id",
            how="left",
            validate="one_to_one",
        )
        ward_output = self.analytics["analytics_ward_performance"]
        source_kpis = {
            "report_count": len(reports),
            "total_waste_kg": float(reports["quantity_kg"].sum()),
            "collection_requests": len(requests),
            "collected_requests": int(requests["status"].eq("COLLECTED").sum()),
            "rating_count": len(ratings),
            "good_ratings": int(ratings["rating"].isin([4, 5]).sum()),
            "average_rating": float(ratings["rating"].mean()),
        }
        analytics_kpis = {
            "report_count": int(ward_output["report_count"].sum()),
            "total_waste_kg": float(ward_output["total_waste_kg"].sum()),
            "collection_requests": int(ward_output["collection_requests"].sum()),
            "collected_requests": int(ward_output["collected_requests"].sum()),
            "rating_count": int(ward_output["rating_count"].sum()),
            "good_ratings": int(ward_output["good_ratings"].sum()),
            "average_rating": float(
                (
                    ward_output["average_segregation_rating"]
                    * ward_output["rating_count"]
                ).sum()
                / ward_output["rating_count"].sum()
            ),
        }
        source_kpis["collection_efficiency_pct"] = (
            100 * source_kpis["collected_requests"] / source_kpis["collection_requests"]
        )
        analytics_kpis["collection_efficiency_pct"] = (
            100 * analytics_kpis["collected_requests"]
            / analytics_kpis["collection_requests"]
        )
        source_kpis["good_segregation_rate_pct"] = (
            100 * source_kpis["good_ratings"] / source_kpis["rating_count"]
        )
        analytics_kpis["good_segregation_rate_pct"] = (
            100 * analytics_kpis["good_ratings"] / analytics_kpis["rating_count"]
        )
        passed = all(
            abs(source_kpis[key] - analytics_kpis[key]) < 0.01
            for key in source_kpis
        )
        actual = {
            "source": {key: round(value, 4) for key, value in source_kpis.items()},
            "analytics": {key: round(value, 4) for key, value in analytics_kpis.items()},
        }
        self.check(16, "Source-to-analytics KPI reconciliation", actual, "equal within 0.01", passed)

    def test_17_priority_score_range(self) -> None:
        scores = self.analytics["analytics_ward_priority_score"]["priority_score"]
        actual = {
            "min": float(scores.min()),
            "max": float(scores.max()),
            "out_of_range": int((~scores.between(0, 100)).sum()),
        }
        self.check(
            17,
            "Priority score range 0-100",
            actual,
            {"min": actual["min"], "max": actual["max"], "out_of_range": 0},
        )

    def test_18_collection_efficiency_range(self) -> None:
        values = self.analytics["analytics_ward_performance"][
            "collection_efficiency_pct"
        ].dropna()
        actual = {
            "min": float(values.min()),
            "max": float(values.max()),
            "out_of_range": int((~values.between(0, 100)).sum()),
        }
        self.check(
            18,
            "Collection efficiency range 0-100",
            actual,
            {"min": actual["min"], "max": actual["max"], "out_of_range": 0},
        )

    def test_19_segregation_percentage_range(self) -> None:
        values = self.analytics["analytics_ward_performance"][
            "good_segregation_rate_pct"
        ].dropna()
        actual = {
            "min": float(values.min()),
            "max": float(values.max()),
            "out_of_range": int((~values.between(0, 100)).sum()),
        }
        self.check(
            19,
            "Good-segregation percentage range 0-100",
            actual,
            {"min": actual["min"], "max": actual["max"], "out_of_range": 0},
        )

    def test_20_ward_analytics_coverage(self) -> None:
        analytics_wards = set(
            self.analytics["analytics_ward_performance"]["ward_id"].dropna().astype(int)
        )
        source_wards = set(self.frames["municipal_wards"]["ward_id"].astype(int))
        actual = {
            "ward_rows": len(self.analytics["analytics_ward_performance"]),
            "unique_wards": len(analytics_wards),
            "missing_wards": len(source_wards - analytics_wards),
            "unexpected_wards": len(analytics_wards - source_wards),
        }
        expected = {
            "ward_rows": 85,
            "unique_wards": 85,
            "missing_wards": 0,
            "unexpected_wards": 0,
        }
        self.check(20, "Exactly 85 wards represented in ward analytics", actual, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
