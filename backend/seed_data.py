"""Seed and verify deterministic Bhopal development data.

Run from the backend directory:
    .\\venv\\Scripts\\python.exe seed_data.py
    .\\venv\\Scripts\\python.exe seed_data.py --reset-generated

The seeder preserves municipal wards and existing areas. It adds one
provisional polygon-backed area to a ward only when that ward has no area.
"""

import argparse
import json
import os
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from passlib.context import CryptContext
from shapely.geometry import Point, shape
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import SessionLocal
from models import (
    Alert,
    Area,
    CollectionRequest,
    Complaint,
    MunicipalWard,
    Penalty,
    RewardTransaction,
    SegregationRating,
    Team,
    TeamMember,
    User,
    Vehicle,
    VehicleLocation,
    WasteReport,
    Worker,
)


SEED_NAME = "bhopal-development-v1"
SEED_CITIZEN_WARD_TABLE = "development_seed_citizen_wards"
SEED_EMAIL_PREFIX = "seed."
SEED_VEHICLE_PREFIX = "SEED-MP28-"
DEVELOPMENT_PASSWORD = "BhopalDev123!"
DEFAULT_SEED = 42
HISTORY_DAYS = 270
REPORT_COUNT = 2_000
CITIZEN_COUNT = 1_000
WORKER_COUNT = 50
COMPLAINT_COUNT = 200
VEHICLE_COUNT = 10
GPS_COUNT = 2_000
REQUEST_RATE_PER_STAFFED_REPORT = 0.80
RATING_RATE_PER_COLLECTED_REQUEST = 0.80
DAILY_WASTE_PER_PERSON_KG = 0.45
DEVELOPMENT_PASSWORD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")
OPERATIONS_ACCOUNT_EMAIL_ENV = "MONITOR_ADMIN_EMAIL"
OPERATIONS_ACCOUNT_PASSWORD_ENV = "MONITOR_ADMIN_PASSWORD"

WASTE_TYPES = (
    "Plastic",
    "Organic",
    "Paper",
    "Glass",
    "Metal",
    "E-Waste",
    "Mixed",
    "Other",
)
WASTE_TYPE_WEIGHTS = (0.16, 0.28, 0.13, 0.08, 0.07, 0.04, 0.18, 0.06)
WASTE_QUANTITY_FACTORS = {
    "Plastic": 1.0,
    "Organic": 1.25,
    "Paper": 0.9,
    "Glass": 0.65,
    "Metal": 0.8,
    "E-Waste": 0.45,
    "Mixed": 1.05,
    "Other": 0.8,
}
PRIORITIES = ("LOW", "NORMAL", "HIGH", "URGENT")
PRIORITY_WEIGHTS = (0.25, 0.58, 0.14, 0.03)
RATING_VALUES = (5, 4, 3, 2, 1)
RATING_WEIGHTS = (0.25, 0.35, 0.25, 0.10, 0.05)
COMPLAINT_CATEGORIES = (
    "MISSED_COLLECTION",
    "ILLEGAL_DUMPING",
    "OVERFLOWING_BIN",
    "SEGREGATION",
    "OTHER",
)
COMPLAINT_CATEGORY_WEIGHTS = (0.35, 0.16, 0.20, 0.14, 0.15)

TABLE_MODELS = {
    "areas": (Area, "area_id"),
    "users": (User, "user_id"),
    "workers": (Worker, "worker_id"),
    "vehicles": (Vehicle, "vehicle_id"),
    "teams": (Team, "team_id"),
    "team_members": (TeamMember, "worker_id"),
    "waste_reports": (WasteReport, "report_id"),
    "collection_requests": (CollectionRequest, "request_id"),
    "segregation_ratings": (SegregationRating, "rating_id"),
    "reward_transactions": (RewardTransaction, "transaction_id"),
    "penalties": (Penalty, "penalty_id"),
    "complaints": (Complaint, "complaint_id"),
    "vehicle_locations": (VehicleLocation, "location_id"),
    "alerts": (Alert, "alert_id"),
}

RESET_ORDER = (
    "alerts",
    "team_members",
    "teams",
    "reward_transactions",
    "penalties",
    "segregation_ratings",
    "collection_requests",
    "complaints",
    "vehicle_locations",
    "waste_reports",
    "vehicles",
    "workers",
    "users",
    "areas",
)


def ensure_development_operations_account(db: Session) -> bool:
    existing_operations_user = (
        db.query(User.user_id)
        .filter(User.role.in_(("ADMIN", "MONITOR")))
        .first()
    )
    if existing_operations_user is not None:
        print("An ADMIN/MONITOR account already exists; no account was added.")
        return False

    email = os.getenv(OPERATIONS_ACCOUNT_EMAIL_ENV, "").strip()
    password = os.getenv(OPERATIONS_ACCOUNT_PASSWORD_ENV, "")
    if not email or not password:
        print(
            "No ADMIN/MONITOR account exists. Set "
            f"{OPERATIONS_ACCOUNT_EMAIL_ENV} and "
            f"{OPERATIONS_ACCOUNT_PASSWORD_ENV} to seed one."
        )
        return False
    if "@" not in email or len(email) > 150:
        raise ValueError(f"{OPERATIONS_ACCOUNT_EMAIL_ENV} must be a valid email.")
    password_bytes = password.encode("utf-8")
    if not 12 <= len(password_bytes) <= 72:
        raise ValueError(
            f"{OPERATIONS_ACCOUNT_PASSWORD_ENV} must contain 12 to 72 UTF-8 bytes."
        )
    if db.query(User.user_id).filter(User.email == email).first() is not None:
        raise RuntimeError(
            "The configured operations email already belongs to a non-ADMIN/"
            "MONITOR account; refusing to change that account."
        )

    role = os.getenv("MONITOR_ADMIN_ROLE", "ADMIN").strip().upper()
    if role not in {"ADMIN", "MONITOR"}:
        raise ValueError("MONITOR_ADMIN_ROLE must be ADMIN or MONITOR.")
    name = os.getenv("MONITOR_ADMIN_NAME", "Development Administrator").strip()
    if not name or len(name) > 100:
        raise ValueError("MONITOR_ADMIN_NAME must contain 1 to 100 characters.")

    db.add(
        User(
            name=name,
            email=email,
            password_hash=DEVELOPMENT_PASSWORD_CONTEXT.hash(password),
            role=role,
            created_at=datetime.now(),
        )
    )
    db.commit()
    print(
        f"Seeded a {role} development account. The password was stored as a hash; "
        "credentials were not printed."
    )
    return True


def ensure_registry(db: Session) -> None:
    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS development_seed_records (
                seed_name VARCHAR(100) NOT NULL,
                table_name VARCHAR(100) NOT NULL,
                record_id BIGINT NOT NULL,
                PRIMARY KEY (seed_name, table_name, record_id)
            )
            """
        )
    )
    db.execute(
        text(
            f"""
            CREATE TABLE IF NOT EXISTS {SEED_CITIZEN_WARD_TABLE} (
                seed_name VARCHAR(100) NOT NULL,
                citizen_id INTEGER NOT NULL REFERENCES users(user_id),
                ward_id INTEGER NOT NULL REFERENCES municipal_wards(ward_id),
                PRIMARY KEY (seed_name, citizen_id)
            )
            """
        )
    )


def register_rows(db: Session, table_name: str, rows: list) -> None:
    if not rows:
        return
    _, id_field = TABLE_MODELS[table_name]
    db.execute(
        text(
            """
            INSERT INTO development_seed_records (seed_name, table_name, record_id)
            VALUES (:seed_name, :table_name, :record_id)
            """
        ),
        [
            {
                "seed_name": SEED_NAME,
                "table_name": table_name,
                "record_id": getattr(row, id_field),
            }
            for row in rows
        ],
    )


def load_manifest(db: Session) -> dict[str, list[int]]:
    ensure_registry(db)
    entries = db.execute(
        text(
            """
            SELECT table_name, record_id
            FROM development_seed_records
            WHERE seed_name = :seed_name
            ORDER BY table_name, record_id
            """
        ),
        {"seed_name": SEED_NAME},
    ).all()
    manifest: dict[str, list[int]] = defaultdict(list)
    for table_name, record_id in entries:
        if table_name not in TABLE_MODELS:
            raise RuntimeError(
                f"Unknown table {table_name!r} in the development seed registry."
            )
        manifest[table_name].append(record_id)
    return dict(manifest)


def persist_citizen_wards(
    db: Session,
    citizens: list[User],
    reports: list[WasteReport],
    area_ward: dict[int, int],
    demand_by_ward: dict[int, float],
    rng: random.Random,
) -> dict[int, int]:
    reports_by_ward: dict[int, list[WasteReport]] = defaultdict(list)
    for report in reports:
        ward_id = area_ward.get(report.area_id)
        if ward_id is None:
            raise RuntimeError(
                f"Report {report.report_id} has no ward-backed operational area."
            )
        reports_by_ward[ward_id].append(report)

    citizen_counts = {ward_id: 1 for ward_id in demand_by_ward}
    capacities = {
        ward_id: len(reports_by_ward.get(ward_id, []))
        for ward_id in demand_by_ward
    }
    if any(capacity < 1 for capacity in capacities.values()):
        raise RuntimeError(
            "Every ward must have at least one generated report before citizens "
            "can be allocated to their home ward."
        )
    if len(citizens) > len(reports):
        raise RuntimeError(
            "The citizen target cannot exceed report count when every generated "
            "citizen must have a report in their mapped ward."
        )
    remaining = len(citizens) - len(citizen_counts)
    if remaining < 0:
        raise RuntimeError("Citizen count is below the number of municipal wards.")
    while remaining:
        eligible = [
            ward_id
            for ward_id, count in citizen_counts.items()
            if count < capacities[ward_id]
        ]
        if not eligible:
            raise RuntimeError(
                "Ward report volumes do not have capacity for the citizen target."
            )
        ward_id = rng.choices(
            eligible,
            weights=[demand_by_ward[item] for item in eligible],
            k=1,
        )[0]
        citizen_counts[ward_id] += 1
        remaining -= 1

    shuffled_citizens = list(citizens)
    rng.shuffle(shuffled_citizens)
    citizen_ward: dict[int, int] = {}
    offset = 0
    citizens_by_ward: dict[int, list[User]] = defaultdict(list)
    for ward_id in sorted(citizen_counts):
        ward_citizens = shuffled_citizens[
            offset : offset + citizen_counts[ward_id]
        ]
        offset += citizen_counts[ward_id]
        citizens_by_ward[ward_id] = ward_citizens
        for citizen in ward_citizens:
            citizen_ward[citizen.user_id] = ward_id

    for ward_id, ward_reports in reports_by_ward.items():
        ward_citizens = citizens_by_ward.get(ward_id, [])
        if len(ward_reports) < len(ward_citizens):
            raise RuntimeError(
                f"Ward {ward_id} has fewer reports than mapped citizens."
            )
        rng.shuffle(ward_reports)
        rng.shuffle(ward_citizens)
        for report, citizen in zip(ward_reports, ward_citizens):
            report.citizen_id = citizen.user_id
        for report in ward_reports[len(ward_citizens) :]:
            report.citizen_id = rng.choice(ward_citizens).user_id

    db.execute(
        text(
            f"""
            INSERT INTO {SEED_CITIZEN_WARD_TABLE}
                (seed_name, citizen_id, ward_id)
            VALUES (:seed_name, :citizen_id, :ward_id)
            ON CONFLICT (seed_name, citizen_id)
            DO UPDATE SET ward_id = EXCLUDED.ward_id
            """
        ),
        [
            {
                "seed_name": SEED_NAME,
                "citizen_id": citizen_id,
                "ward_id": ward_id,
            }
            for citizen_id, ward_id in citizen_ward.items()
        ],
    )
    return citizen_ward


def rows_from_manifest(db: Session, manifest: dict[str, list[int]]) -> dict[str, list]:
    rows: dict[str, list] = {}
    for table_name, (model, id_field) in TABLE_MODELS.items():
        ids = manifest.get(table_name, [])
        if ids:
            records = (
                db.query(model)
                .filter(getattr(model, id_field).in_(ids))
                .order_by(getattr(model, id_field))
                .all()
            )
        else:
            records = []
        if len(records) != len(ids):
            raise RuntimeError(
                f"The seed registry references missing {table_name} records."
            )
        rows[table_name] = records
    return rows


def add_rows(db: Session, table_name: str, rows: list) -> None:
    if not rows:
        return
    db.add_all(rows)
    db.flush()
    register_rows(db, table_name, rows)


def get_ward_geometries(wards: list[MunicipalWard]) -> dict[int, object]:
    geometries = {}
    for ward in wards:
        if not ward.boundary_geojson:
            raise RuntimeError(
                f"Ward {ward.ward_number} has no stored GeoJSON boundary."
            )
        try:
            geometry = shape(json.loads(ward.boundary_geojson))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Ward {ward.ward_number} has invalid stored GeoJSON."
            ) from exc
        if geometry.is_empty or not geometry.is_valid:
            raise RuntimeError(
                f"Ward {ward.ward_number} has an empty or invalid boundary."
            )
        geometries[ward.ward_id] = geometry
    return geometries


def get_area_geometries(
    areas: list[Area],
    ward_geometries: dict[int, object],
) -> dict[int, object]:
    geometries = {}
    for area in areas:
        if area.ward_id not in ward_geometries:
            raise RuntimeError(
                f"Area {area.area_id} ({area.area_name}) is not linked to a "
                "municipal ward with a valid boundary."
            )
        ward_geometry = ward_geometries[area.ward_id]
        if area.boundary_geojson:
            try:
                geometry = shape(json.loads(area.boundary_geojson))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"Area {area.area_id} has invalid stored GeoJSON."
                ) from exc
            if geometry.is_empty or not geometry.is_valid:
                raise RuntimeError(f"Area {area.area_id} has an invalid boundary.")
            if not ward_geometry.covers(geometry):
                geometry = geometry.intersection(ward_geometry)
                if geometry.is_empty or not geometry.is_valid:
                    raise RuntimeError(
                        f"Area {area.area_id} has no valid overlap with ward "
                        f"{area.ward_id}."
                    )
        else:
            geometry = ward_geometry
        geometries[area.area_id] = geometry
    return geometries


def point_inside(rng: random.Random, geometry) -> Point:
    min_x, min_y, max_x, max_y = geometry.bounds
    for _ in range(2_000):
        point = Point(
            round(rng.uniform(min_x, max_x), 6),
            round(rng.uniform(min_y, max_y), 6),
        )
        if geometry.covers(point):
            return point
    representative = geometry.representative_point()
    fallback = Point(round(representative.x, 6), round(representative.y, 6))
    if not geometry.covers(fallback):
        raise RuntimeError("Could not find a point inside an area boundary.")
    return fallback


def area_weights(areas: list[Area], geometry_by_area: dict[int, object]) -> list[float]:
    return [max(geometry_by_area[area.area_id].area, 1e-12) for area in areas]


def create_provisional_areas(
    db: Session,
    wards: list[MunicipalWard],
) -> tuple[dict[int, list[Area]], int]:
    all_areas = db.query(Area).order_by(Area.area_id).all()
    areas_by_ward: dict[int, list[Area]] = defaultdict(list)
    for area in all_areas:
        if area.ward_id is not None:
            areas_by_ward[area.ward_id].append(area)

    created = []
    for ward in wards:
        if areas_by_ward.get(ward.ward_id):
            continue
        boundary = json.loads(ward.boundary_geojson)
        area = Area(
            area_name=(
                f"Ward {ward.ward_number} - {ward.ward_name} "
                "Operational Area 01 (Provisional)"
            ),
            locality_name="Provisional ward-backed operational area",
            ward_id=ward.ward_id,
            boundary_geojson=json.dumps(boundary, ensure_ascii=False),
            status="ACTIVE",
        )
        db.add(area)
        db.flush()
        areas_by_ward[ward.ward_id].append(area)
        created.append(area)
    register_rows(db, "areas", created)
    return dict(areas_by_ward), len(created)


def build_demand_weights(
    rng: random.Random,
    wards: list[MunicipalWard],
) -> dict[int, float]:
    known_populations = [
        ward.population
        for ward in wards
        if ward.population is not None and ward.population > 0
    ]
    if not known_populations:
        raise RuntimeError("No wards have a usable population demand prior.")
    sorted_populations = sorted(known_populations)
    middle = len(sorted_populations) // 2
    if len(sorted_populations) % 2:
        neutral_population_weight = float(sorted_populations[middle])
    else:
        neutral_population_weight = (
            sorted_populations[middle - 1] + sorted_populations[middle]
        ) / 2

    varied_daily_demand = {}
    for ward in wards:
        population_weight = (
            float(ward.population)
            if ward.population is not None and ward.population > 0
            else neutral_population_weight
        )
        controlled_variation = rng.uniform(0.85, 1.15)
        varied_daily_demand[ward.ward_id] = (
            population_weight
            * DAILY_WASTE_PER_PERSON_KG
            * controlled_variation
        )
    return varied_daily_demand


def create_users_and_workers(
    db: Session,
    rng: random.Random,
    wards: list[MunicipalWard],
    areas_by_ward: dict[int, list[Area]],
    demand_by_ward: dict[int, float],
    citizen_count: int,
    worker_count: int,
) -> tuple[list[User], list[Worker], dict[int, Area]]:
    generated_emails = [
        f"{SEED_EMAIL_PREFIX}citizen{index:03d}@example.com"
        for index in range(1, citizen_count + 1)
    ] + [
        f"{SEED_EMAIL_PREFIX}worker{index:03d}@example.com"
        for index in range(1, worker_count + 1)
    ]
    email_collisions = (
        db.query(User.email).filter(User.email.in_(generated_emails)).all()
    )
    if email_collisions:
        raise RuntimeError(
            "Generated user email collision(s) exist without a matching seed "
            "registry; refusing to reuse or modify those users."
        )

    ward_order = sorted(
        wards,
        key=lambda ward: (-demand_by_ward[ward.ward_id], ward.ward_id),
    )
    staffed_wards = ward_order[:worker_count]
    if len(staffed_wards) < worker_count:
        raise RuntimeError("There are fewer wards than requested development workers.")
    staffed_area_by_ward = {
        ward.ward_id: sorted(
            areas_by_ward[ward.ward_id],
            key=lambda area: area.area_id,
        )[0]
        for ward in staffed_wards
    }

    password_hash = DEVELOPMENT_PASSWORD_CONTEXT.hash(DEVELOPMENT_PASSWORD)
    names = (
        "Aarav Sharma",
        "Ananya Patel",
        "Rohan Verma",
        "Meera Gupta",
        "Kabir Singh",
        "Isha Joshi",
        "Vivaan Jain",
        "Diya Nair",
        "Arjun Mishra",
        "Kavya Rao",
        "Ishaan Shah",
        "Aditi Dubey",
        "Manav Tiwari",
        "Neha Sinha",
        "Yash Choudhary",
        "Riya Malhotra",
        "Kunal Mehta",
        "Pooja Thakur",
        "Aditya Kapoor",
        "Sanya Iyer",
    )
    citizens = [
        User(
            name=names[(index - 1) % len(names)],
            email=f"{SEED_EMAIL_PREFIX}citizen{index:03d}@example.com",
            password_hash=password_hash,
            role="CITIZEN",
            created_at=datetime.now() - timedelta(days=rng.randint(1, 365)),
        )
        for index in range(1, citizen_count + 1)
    ]
    add_rows(db, "users", citizens)

    worker_users = [
        User(
            name=f"Development Collection Worker {index:02d}",
            email=f"{SEED_EMAIL_PREFIX}worker{index:03d}@example.com",
            password_hash=password_hash,
            role="WORKER",
            created_at=datetime.now() - timedelta(days=rng.randint(1, 365)),
        )
        for index in range(1, worker_count + 1)
    ]
    add_rows(db, "users", worker_users)

    workers = [
        Worker(
            user_id=user.user_id,
            assigned_area=staffed_area_by_ward[ward.ward_id].area_id,
        )
        for user, ward in zip(worker_users, staffed_wards)
    ]
    add_rows(db, "workers", workers)
    worker_area_by_id = {
        worker.worker_id: staffed_area_by_ward[ward.ward_id]
        for worker, ward in zip(workers, staffed_wards)
    }
    return citizens, workers, worker_area_by_id


def add_missing_citizens(
    db: Session,
    rng: random.Random,
    citizens: list[User],
    target_count: int,
) -> list[User]:
    if len(citizens) > target_count:
        raise RuntimeError(
            f"Found {len(citizens)} generated citizens, above the requested "
            f"target {target_count}; refusing to delete any user."
        )
    names = (
        "Aarav Sharma", "Ananya Patel", "Rohan Verma", "Meera Gupta",
        "Kabir Singh", "Isha Joshi", "Vivaan Jain", "Diya Nair",
        "Arjun Mishra", "Kavya Rao", "Ishaan Shah", "Aditi Dubey",
        "Manav Tiwari", "Neha Sinha", "Yash Choudhary", "Riya Malhotra",
        "Kunal Mehta", "Pooja Thakur", "Aditya Kapoor", "Sanya Iyer",
    )
    first_new_index = len(citizens) + 1
    emails = [
        f"{SEED_EMAIL_PREFIX}citizen{index:03d}@example.com"
        for index in range(first_new_index, target_count + 1)
    ]
    if emails and db.query(User.user_id).filter(User.email.in_(emails)).first():
        raise RuntimeError(
            "An unregistered generated citizen email already exists; refusing "
            "to reuse or modify it."
        )
    password_hash = DEVELOPMENT_PASSWORD_CONTEXT.hash(DEVELOPMENT_PASSWORD)
    additions = [
        User(
            name=names[(index - 1) % len(names)],
            email=f"{SEED_EMAIL_PREFIX}citizen{index:03d}@example.com",
            password_hash=password_hash,
            role="CITIZEN",
            created_at=datetime.now() - timedelta(days=rng.randint(1, 365)),
        )
        for index in range(first_new_index, target_count + 1)
    ]
    add_rows(db, "users", additions)
    return [*citizens, *additions]


def add_missing_workers(
    db: Session,
    rng: random.Random,
    workers: list[Worker],
    target_count: int,
    all_areas: list[Area],
    demand_by_ward: dict[int, float],
    reports: list[WasteReport],
    requests: list[CollectionRequest],
) -> tuple[list[Worker], dict[int, Area], set[int]]:
    if len(workers) > target_count:
        raise RuntimeError(
            f"Found {len(workers)} generated workers, above the requested "
            f"target {target_count}; refusing to delete any worker."
        )
    required = target_count - len(workers)
    if required == 0:
        return workers, {}, set()
    existing_worker_areas = {worker.assigned_area for worker in workers}
    existing_team_areas = {
        team.area_id for team in db.query(Team).all()
    }
    request_by_report = {request.report_id: request for request in requests}
    reports_by_area: dict[int, list[WasteReport]] = defaultdict(list)
    for report in reports:
        reports_by_area[report.area_id].append(report)
    candidates = [
        area
        for area in all_areas
        if area.area_id not in existing_worker_areas
        and area.area_id not in existing_team_areas
        and reports_by_area.get(area.area_id)
    ]
    if len(candidates) < required:
        raise RuntimeError(
            f"Only {len(candidates)} unstaffed report-bearing areas are available "
            f"for {required} additional workers; refusing unrelated assignments."
        )

    metrics = {}
    for area in candidates:
        area_reports = reports_by_area[area.area_id]
        metrics[area.area_id] = {
            "demand": demand_by_ward[area.ward_id],
            "waste": sum(float(report.quantity_kg) for report in area_reports),
            "workload": sum(
                request_by_report.get(report.report_id) is None
                or request_by_report[report.report_id].status != "COLLECTED"
                for report in area_reports
            ),
        }

    def normalized(metric: str) -> dict[int, float]:
        values = [float(values[metric]) for values in metrics.values()]
        lower, upper = min(values), max(values)
        if lower == upper:
            return {area_id: 0.0 for area_id in metrics}
        return {
            area_id: (float(values[metric]) - lower) / (upper - lower)
            for area_id, values in metrics.items()
        }

    demand_score = normalized("demand")
    waste_score = normalized("waste")
    workload_score = normalized("workload")
    scores = {
        area.area_id: (
            0.40 * demand_score[area.area_id]
            + 0.35 * waste_score[area.area_id]
            + 0.25 * workload_score[area.area_id]
        )
        for area in candidates
    }
    selected_areas = sorted(
        candidates,
        key=lambda area: (-scores[area.area_id], area.area_id),
    )[:required]

    first_new_index = len(workers) + 1
    emails = [
        f"{SEED_EMAIL_PREFIX}worker{index:03d}@example.com"
        for index in range(first_new_index, target_count + 1)
    ]
    if db.query(User.user_id).filter(User.email.in_(emails)).first():
        raise RuntimeError(
            "An unregistered generated worker email already exists; refusing "
            "to reuse or modify it."
        )
    password_hash = DEVELOPMENT_PASSWORD_CONTEXT.hash(DEVELOPMENT_PASSWORD)
    worker_users = [
        User(
            name=f"Development Collection Worker {index:02d}",
            email=f"{SEED_EMAIL_PREFIX}worker{index:03d}@example.com",
            password_hash=password_hash,
            role="WORKER",
            created_at=datetime.now() - timedelta(days=rng.randint(1, 365)),
        )
        for index in range(first_new_index, target_count + 1)
    ]
    add_rows(db, "users", worker_users)
    additions = [
        Worker(user_id=user.user_id, assigned_area=area.area_id)
        for user, area in zip(worker_users, selected_areas)
    ]
    add_rows(db, "workers", additions)

    vehicles = db.query(Vehicle).filter(
        Vehicle.vehicle_number.like(f"{SEED_VEHICLE_PREFIX}%")
    ).order_by(Vehicle.vehicle_id).all()
    if not vehicles:
        raise RuntimeError(
            "No registered development vehicles are available to associate "
            "with the added operational teams."
        )
    teams = [
        Team(
            team_name=f"Development Collection Team {worker.worker_id:03d}",
            area_id=area.area_id,
            leader_worker_id=worker.worker_id,
            vehicle_id=vehicles[index % len(vehicles)].vehicle_id,
        )
        for index, (worker, area) in enumerate(zip(additions, selected_areas))
    ]
    add_rows(db, "teams", teams)
    team_members = [
        TeamMember(team_id=team.team_id, worker_id=team.leader_worker_id)
        for team in teams
    ]
    add_rows(db, "team_members", team_members)
    area_by_worker = {
        worker.worker_id: area
        for worker, area in zip(additions, selected_areas)
    }
    return (
        [*workers, *additions],
        area_by_worker,
        {area.area_id for area in selected_areas},
    )


def create_reports(
    db: Session,
    rng: random.Random,
    wards: list[MunicipalWard],
    areas_by_ward: dict[int, list[Area]],
    ward_geometries: dict[int, object],
    area_geometries: dict[int, object],
    citizens: list[User],
    demand_by_ward: dict[int, float],
    report_count: int,
) -> list[WasteReport]:
    now = datetime.now()
    start = now - timedelta(days=HISTORY_DAYS)
    ward_weights = [demand_by_ward[ward.ward_id] for ward in wards]
    reports = []
    for _ in range(report_count):
        ward = rng.choices(wards, weights=ward_weights, k=1)[0]
        ward_areas = areas_by_ward[ward.ward_id]
        area = rng.choices(
            ward_areas,
            weights=area_weights(ward_areas, area_geometries),
            k=1,
        )[0]
        point = point_inside(rng, area_geometries[area.area_id])
        if not ward_geometries[ward.ward_id].covers(point):
            raise RuntimeError(
                f"Generated report point fell outside ward {ward.ward_number}."
            )
        waste_type = rng.choices(
            WASTE_TYPES,
            weights=WASTE_TYPE_WEIGHTS,
            k=1,
        )[0]
        quantity = min(
            50.0,
            max(
                0.5,
                rng.triangular(0.5, 50.0, 11.0)
                * WASTE_QUANTITY_FACTORS[waste_type],
            ),
        )
        reported_at = start + timedelta(
            seconds=rng.randint(0, int((now - start).total_seconds()))
        )
        reports.append(
            WasteReport(
                citizen_id=rng.choice(citizens).user_id,
                area_id=area.area_id,
                waste_type=waste_type,
                quantity_kg=round(quantity, 2),
                latitude=round(point.y, 6),
                longitude=round(point.x, 6),
                priority=rng.choices(
                    PRIORITIES,
                    weights=PRIORITY_WEIGHTS,
                    k=1,
                )[0],
                status="PENDING",
                reported_at=reported_at,
            )
        )
    add_rows(db, "waste_reports", reports)
    return reports


def create_collections(
    db: Session,
    rng: random.Random,
    reports: list[WasteReport],
    workers: list[Worker],
) -> list[CollectionRequest]:
    workers_by_area: dict[int, list[Worker]] = defaultdict(list)
    for worker in workers:
        workers_by_area[worker.assigned_area].append(worker)

    now = datetime.now()
    requests = []
    for report in reports:
        matching_workers = workers_by_area.get(report.area_id, [])
        if not matching_workers or rng.random() >= REQUEST_RATE_PER_STAFFED_REPORT:
            continue
        worker = rng.choice(matching_workers)
        assigned_at = min(
            report.reported_at + timedelta(hours=rng.randint(1, 96)),
            now,
        )
        status_roll = rng.random()
        if status_roll < 0.82:
            status = "COLLECTED"
            collected_at = min(
                assigned_at + timedelta(hours=rng.randint(1, 48)),
                now,
            )
            report.status = "COLLECTED"
        elif status_roll < 0.93:
            status = "IN_PROGRESS"
            collected_at = None
            report.status = "ASSIGNED"
        else:
            status = "ASSIGNED"
            collected_at = None
            report.status = "ASSIGNED"
        requests.append(
            CollectionRequest(
                report_id=report.report_id,
                worker_id=worker.worker_id,
                assigned_at=assigned_at,
                collected_at=collected_at,
                status=status,
            )
        )

    add_rows(db, "collection_requests", requests)
    return requests


def create_collections_for_newly_staffed_areas(
    db: Session,
    rng: random.Random,
    reports: list[WasteReport],
    workers: list[Worker],
    newly_staffed_area_ids: set[int],
    existing_requests: list[CollectionRequest],
) -> list[CollectionRequest]:
    workers_by_area: dict[int, list[Worker]] = defaultdict(list)
    for worker in workers:
        workers_by_area[worker.assigned_area].append(worker)
    requested_report_ids = {
        request.report_id for request in existing_requests
    }
    now = datetime.now()
    additions = []
    for report in sorted(reports, key=lambda item: item.report_id):
        if (
            report.area_id not in newly_staffed_area_ids
            or report.report_id in requested_report_ids
            or rng.random() >= REQUEST_RATE_PER_STAFFED_REPORT
        ):
            continue
        matching_workers = workers_by_area.get(report.area_id, [])
        if not matching_workers:
            raise RuntimeError(
                f"Newly staffed area {report.area_id} has no matching worker."
            )
        worker = rng.choice(matching_workers)
        assigned_at = min(
            report.reported_at + timedelta(hours=rng.randint(1, 96)),
            now,
        )
        status_roll = rng.random()
        if status_roll < 0.82:
            status = "COLLECTED"
            collected_at = min(
                assigned_at + timedelta(hours=rng.randint(1, 48)),
                now,
            )
            report.status = "COLLECTED"
        elif status_roll < 0.93:
            status = "IN_PROGRESS"
            collected_at = None
            report.status = "ASSIGNED"
        else:
            status = "ASSIGNED"
            collected_at = None
            report.status = "ASSIGNED"
        additions.append(
            CollectionRequest(
                report_id=report.report_id,
                worker_id=worker.worker_id,
                assigned_at=assigned_at,
                collected_at=collected_at,
                status=status,
            )
        )
    add_rows(db, "collection_requests", additions)
    return additions


def create_ratings_and_incentives(
    db: Session,
    rng: random.Random,
    reports_by_id: dict[int, WasteReport],
    requests: list[CollectionRequest],
) -> tuple[list[SegregationRating], list[RewardTransaction], list[Penalty]]:
    ratings = []
    for request in requests:
        if (
            request.status != "COLLECTED"
            or rng.random() >= RATING_RATE_PER_COLLECTED_REQUEST
        ):
            continue
        report = reports_by_id[request.report_id]
        rating = rng.choices(
            RATING_VALUES,
            weights=RATING_WEIGHTS,
            k=1,
        )[0]
        ratings.append(
            SegregationRating(
                request_id=request.request_id,
                citizen_id=report.citizen_id,
                worker_id=request.worker_id,
                rating=rating,
                remarks={
                    5: "Properly segregated",
                    4: "Good segregation",
                    3: "Mostly correct",
                    2: "Mixed waste found",
                    1: "Poor segregation",
                }[rating],
                rated_at=min(
                    (request.collected_at or datetime.now())
                    + timedelta(hours=rng.randint(1, 24)),
                    datetime.now(),
                ),
            )
        )
    add_rows(db, "segregation_ratings", ratings)

    rewards = []
    penalties = []
    for rating in ratings:
        if rating.rating >= 4:
            rewards.append(
                RewardTransaction(
                    citizen_id=rating.citizen_id,
                    points=rating.rating * 10,
                    transaction_type="SEGREGATION_REWARD",
                    reference_id=rating.rating_id,
                    created_at=rating.rated_at,
                )
            )
        elif rating.rating <= 2:
            penalties.append(
                Penalty(
                    citizen_id=rating.citizen_id,
                    reason=f"Poor segregation rating: {rating.rating}",
                    amount=50.00 if rating.rating == 2 else 100.00,
                    status="PENDING",
                    created_at=rating.rated_at,
                )
            )
    add_rows(db, "reward_transactions", rewards)
    add_rows(db, "penalties", penalties)
    return ratings, rewards, penalties


def create_complaints(
    db: Session,
    rng: random.Random,
    citizens_by_ward: dict[int, list[User]],
    wards: list[MunicipalWard],
    areas_by_ward: dict[int, list[Area]],
    demand_by_ward: dict[int, float],
    complaint_count: int,
) -> list[Complaint]:
    now = datetime.now()
    start = now - timedelta(days=HISTORY_DAYS)
    complaints = []
    for _ in range(complaint_count):
        ward = rng.choices(
            wards,
            weights=[demand_by_ward[item.ward_id] for item in wards],
            k=1,
        )[0]
        area = rng.choice(areas_by_ward[ward.ward_id])
        created_at = start + timedelta(
            seconds=rng.randint(0, int((now - start).total_seconds()))
        )
        status = rng.choices(
            ("OPEN", "IN_PROGRESS", "RESOLVED"),
            weights=(0.35, 0.25, 0.40),
            k=1,
        )[0]
        complaints.append(
            Complaint(
                citizen_id=rng.choice(
                    citizens_by_ward[ward.ward_id]
                ).user_id,
                area_id=area.area_id,
                category=rng.choices(
                    COMPLAINT_CATEGORIES,
                    weights=COMPLAINT_CATEGORY_WEIGHTS,
                    k=1,
                )[0],
                description="Development-data complaint for operational testing.",
                priority=rng.choices(
                    PRIORITIES,
                    weights=PRIORITY_WEIGHTS,
                    k=1,
                )[0],
                status=status,
                created_at=created_at,
                resolved_at=(
                    created_at + timedelta(hours=rng.randint(1, 72))
                    if status == "RESOLVED"
                    else None
                ),
            )
        )
    add_rows(db, "complaints", complaints)
    return complaints


def align_generated_citizen_references(
    rng: random.Random,
    citizens: list[User],
    citizen_ward: dict[int, int],
    reports: list[WasteReport],
    requests: list[CollectionRequest],
    ratings: list[SegregationRating],
    rewards: list[RewardTransaction],
    complaints: list[Complaint],
    area_ward: dict[int, int],
) -> dict[int, list[User]]:
    citizens_by_ward: dict[int, list[User]] = defaultdict(list)
    users_by_id = {user.user_id: user for user in citizens}
    for citizen_id, ward_id in citizen_ward.items():
        user = users_by_id.get(citizen_id)
        if user is not None:
            citizens_by_ward[ward_id].append(user)
    for ward_citizens in citizens_by_ward.values():
        rng.shuffle(ward_citizens)

    reports_by_id = {report.report_id: report for report in reports}
    requests_by_id = {request.request_id: request for request in requests}
    ratings_by_id = {rating.rating_id: rating for rating in ratings}
    for rating in ratings:
        request = requests_by_id.get(rating.request_id)
        report = reports_by_id.get(request.report_id) if request else None
        if report is None:
            raise RuntimeError(
                f"Rating {rating.rating_id} has no generated source report."
            )
        rating.citizen_id = report.citizen_id
    for reward in rewards:
        rating = ratings_by_id.get(reward.reference_id)
        if rating is None:
            raise RuntimeError(
                f"Reward {reward.transaction_id} has no generated rating reference."
            )
        reward.citizen_id = rating.citizen_id
    for complaint in complaints:
        ward_id = area_ward.get(complaint.area_id)
        ward_citizens = citizens_by_ward.get(ward_id, [])
        if not ward_citizens:
            raise RuntimeError(
                f"Complaint {complaint.complaint_id} has no mapped citizen in "
                f"ward {ward_id}."
            )
        complaint.citizen_id = rng.choice(ward_citizens).user_id
    return dict(citizens_by_ward)


def create_vehicles_teams_and_gps(
    db: Session,
    rng: random.Random,
    workers: list[Worker],
    worker_area_by_id: dict[int, Area],
    area_geometries: dict[int, object],
    vehicles_count: int,
    gps_count: int,
) -> tuple[list[Vehicle], list[Team], list[TeamMember], list[VehicleLocation]]:
    numbers = [
        f"{SEED_VEHICLE_PREFIX}{index:03d}"
        for index in range(1, vehicles_count + 1)
    ]
    if db.query(Vehicle.vehicle_id).filter(Vehicle.vehicle_number.in_(numbers)).count():
        raise RuntimeError(
            "Generated vehicle-number collision exists without a matching seed "
            "registry; refusing to reuse or modify those vehicles."
        )

    vehicles = [
        Vehicle(
            vehicle_number=vehicle_number,
            worker_id=workers[index % len(workers)].worker_id,
            status="ACTIVE",
        )
        for index, vehicle_number in enumerate(numbers)
    ]
    add_rows(db, "vehicles", vehicles)

    vehicle_by_worker = {}
    for index, vehicle in enumerate(vehicles):
        worker = workers[index % len(workers)]
        vehicle_by_worker[worker.worker_id] = vehicle

    teams = []
    team_members = []
    for worker in workers:
        area = worker_area_by_id[worker.worker_id]
        team = Team(
            team_name=f"Development Collection Team {worker.worker_id:03d}",
            area_id=area.area_id,
            leader_worker_id=worker.worker_id,
            vehicle_id=(
                vehicle_by_worker[worker.worker_id].vehicle_id
                if worker.worker_id in vehicle_by_worker
                else None
            ),
        )
        teams.append(team)
    add_rows(db, "teams", teams)
    team_members = [
        TeamMember(team_id=team.team_id, worker_id=team.leader_worker_id)
        for team in teams
    ]
    add_rows(db, "team_members", team_members)

    if gps_count % len(vehicles) != 0:
        raise RuntimeError("GPS record count must divide evenly among vehicles.")
    per_vehicle = gps_count // len(vehicles)
    now = datetime.now()
    gps = []
    for vehicle in vehicles:
        area = worker_area_by_id[vehicle.worker_id]
        geometry = area_geometries[area.area_id]
        point = point_inside(rng, geometry)
        start = now - timedelta(days=30)
        for index in range(per_vehicle):
            if index:
                candidate = Point(
                    round(point.x + rng.uniform(-0.001, 0.001), 6),
                    round(point.y + rng.uniform(-0.001, 0.001), 6),
                )
                if geometry.covers(candidate):
                    point = candidate
            gps.append(
                VehicleLocation(
                    vehicle_id=vehicle.vehicle_id,
                    latitude=round(point.y, 6),
                    longitude=round(point.x, 6),
                    recorded_at=start
                    + timedelta(seconds=(30 * 24 * 60 * 60 * index) // per_vehicle),
                )
            )
    add_rows(db, "vehicle_locations", gps)
    return vehicles, teams, team_members, gps


def create_alerts(
    db: Session,
    reports: list[WasteReport],
    complaints: list[Complaint],
    areas_by_ward: dict[int, list[Area]],
) -> list[Alert]:
    report_counts = Counter(report.area_id for report in reports)
    complaint_counts = Counter(complaint.area_id for complaint in complaints)
    staffed_area_ids = {
        area_id for (area_id,) in db.query(Worker.assigned_area).distinct().all()
    }
    alerts = []
    for ward_areas in areas_by_ward.values():
        for area in ward_areas:
            unstaffed = area.area_id not in staffed_area_ids
            if unstaffed and report_counts[area.area_id] >= 5:
                alerts.append(
                    Alert(
                        area_id=area.area_id,
                        alert_type="UNASSIGNED_COLLECTION_DEMAND",
                        severity="HIGH",
                        message=(
                            f"SEED: {report_counts[area.area_id]} historical reports "
                            "have no worker assigned to this operational area."
                        ),
                        created_at=datetime.now(),
                        status="OPEN",
                    )
                )
            if complaint_counts[area.area_id] >= 3:
                alerts.append(
                    Alert(
                        area_id=area.area_id,
                        alert_type="REPEATED_COMPLAINTS",
                        severity="MEDIUM",
                        message=(
                            f"SEED: {complaint_counts[area.area_id]} generated "
                            "complaints were recorded for this operational area."
                        ),
                        created_at=datetime.now(),
                        status="OPEN",
                    )
                )
    add_rows(db, "alerts", alerts)
    return alerts


def validate_seed(
    rows: dict[str, list],
    wards: list[MunicipalWard],
    all_areas: list[Area],
    citizen_ward: dict[int, int],
) -> None:
    users = rows["users"]
    workers = rows["workers"]
    vehicles = rows["vehicles"]
    reports = rows["waste_reports"]
    requests = rows["collection_requests"]
    ratings = rows["segregation_ratings"]
    rewards = rows["reward_transactions"]
    penalties = rows["penalties"]
    complaints = rows["complaints"]
    gps = rows["vehicle_locations"]
    teams = rows["teams"]
    team_members = rows["team_members"]

    users_by_id = {user.user_id: user for user in users}
    workers_by_id = {worker.worker_id: worker for worker in workers}
    vehicles_by_id = {vehicle.vehicle_id: vehicle for vehicle in vehicles}
    reports_by_id = {report.report_id: report for report in reports}
    ratings_by_id = {rating.rating_id: rating for rating in ratings}
    areas_by_id = {area.area_id: area for area in all_areas}
    wards_by_id = {ward.ward_id: ward for ward in wards}
    ward_geometries = get_ward_geometries(wards)
    area_geometries = get_area_geometries(all_areas, ward_geometries)

    generated_emails = [user.email for user in users]
    if len(generated_emails) != len(set(generated_emails)):
        raise RuntimeError("Generated user emails are not unique.")
    generated_vehicle_numbers = [vehicle.vehicle_number for vehicle in vehicles]
    if len(generated_vehicle_numbers) != len(set(generated_vehicle_numbers)):
        raise RuntimeError("Generated vehicle numbers are not unique.")

    if any(worker.user_id not in users_by_id for worker in workers):
        raise RuntimeError("A generated worker references a missing generated user.")
    generated_citizens = {
        user.user_id for user in users if user.role == "CITIZEN"
    }
    if generated_citizens != set(citizen_ward):
        raise RuntimeError(
            "Every generated citizen must have exactly one persisted home ward."
        )
    ward_by_area = {
        area.area_id: area.ward_id
        for area in all_areas
        if area.ward_id is not None
    }
    if len({worker.user_id for worker in workers}) != len(workers):
        raise RuntimeError("A generated worker user has multiple worker records.")
    for worker in workers:
        if worker.assigned_area not in areas_by_id:
            raise RuntimeError(
                f"Worker {worker.worker_id} has no valid operational area."
            )
        if users_by_id[worker.user_id].role != "WORKER":
            raise RuntimeError(
                f"Worker {worker.worker_id} references a non-worker user."
            )
    if any(vehicle.worker_id not in workers_by_id for vehicle in vehicles):
        raise RuntimeError("A generated vehicle references a missing worker.")

    for report in reports:
        area = areas_by_id.get(report.area_id)
        if area is None or area.ward_id not in wards_by_id:
            raise RuntimeError(
                f"Waste report {report.report_id} has no valid ward-backed area."
            )
        if report.citizen_id not in users_by_id:
            raise RuntimeError(
                f"Waste report {report.report_id} references a missing citizen."
            )
        if users_by_id[report.citizen_id].role != "CITIZEN":
            raise RuntimeError(
                f"Waste report {report.report_id} references a non-citizen user."
            )
        if citizen_ward.get(report.citizen_id) != area.ward_id:
            raise RuntimeError(
                f"Waste report {report.report_id} is outside its citizen's "
                "mapped home ward."
            )
        if report.quantity_kg is None or not 0.5 <= float(report.quantity_kg) <= 50:
            raise RuntimeError(
                f"Waste report {report.report_id} has an invalid quantity."
            )
        if report.latitude is None or report.longitude is None:
            raise RuntimeError(
                f"Waste report {report.report_id} has a NULL coordinate."
            )
        point = Point(float(report.longitude), float(report.latitude))
        ward_id = area.ward_id
        if not area_geometries[area.area_id].covers(point):
            raise RuntimeError(
                f"Waste report {report.report_id} is outside its operational area."
            )
        if not ward_geometries[ward_id].covers(point):
            raise RuntimeError(
                f"Waste report {report.report_id} is outside its municipal ward."
            )

    if len(requests) > len(reports):
        raise RuntimeError("Collection requests exceed waste reports.")
    reports_with_requests = set()
    for request in requests:
        report = reports_by_id.get(request.report_id)
        worker = workers_by_id.get(request.worker_id)
        if report is None or worker is None:
            raise RuntimeError(
                f"Collection request {request.request_id} has an orphan reference."
            )
        if worker.assigned_area != report.area_id:
            raise RuntimeError(
                f"Collection request {request.request_id} assigns a worker from "
                "a different operational area."
            )
        if request.report_id in reports_with_requests:
            raise RuntimeError("A generated report has duplicate collection requests.")
        reports_with_requests.add(request.report_id)
        if request.status == "COLLECTED" and request.collected_at is None:
            raise RuntimeError(
                f"Collected request {request.request_id} has no collected_at time."
            )
        if (
            request.status == "COLLECTED"
            and report.status != "COLLECTED"
        ) or (
            request.status != "COLLECTED"
            and report.status != "ASSIGNED"
        ):
            raise RuntimeError(
                f"Report {report.report_id} status does not match collection "
                f"request {request.request_id}."
            )
        if request.status != "COLLECTED" and request.collected_at is not None:
            raise RuntimeError(
                f"Uncollected request {request.request_id} has collected_at set."
            )
    for report in reports:
        if (
            report.report_id not in reports_with_requests
            and report.status != "PENDING"
        ):
            raise RuntimeError(
                f"Report {report.report_id} has no request but is not pending."
            )

    collected_requests = {
        request.request_id: request
        for request in requests
        if request.status == "COLLECTED"
    }
    if len(ratings) > len(collected_requests):
        raise RuntimeError("Ratings exceed collected collection requests.")
    for rating in ratings:
        request = collected_requests.get(rating.request_id)
        report = reports_by_id.get(request.report_id) if request else None
        if request is None or report is None:
            raise RuntimeError(
                f"Segregation rating {rating.rating_id} is not linked to a "
                "collected request."
            )
        if rating.citizen_id != report.citizen_id:
            raise RuntimeError(
                f"Segregation rating {rating.rating_id} has the wrong citizen."
            )
        if rating.worker_id != request.worker_id or rating.worker_id not in workers_by_id:
            raise RuntimeError(
                f"Segregation rating {rating.rating_id} has the wrong worker."
            )
    for reward in rewards:
        rating = ratings_by_id.get(reward.reference_id)
        if rating is None or reward.citizen_id != rating.citizen_id:
            raise RuntimeError(
                f"Reward {reward.transaction_id} has an invalid rating reference."
            )
    for penalty in penalties:
        if (
            penalty.citizen_id not in users_by_id
            or users_by_id[penalty.citizen_id].role != "CITIZEN"
        ):
            raise RuntimeError(
                f"Penalty {penalty.penalty_id} has an invalid citizen reference."
            )
    for complaint in complaints:
        if (
            complaint.citizen_id not in users_by_id
            or complaint.area_id not in areas_by_id
        ):
            raise RuntimeError(
                f"Complaint {complaint.complaint_id} has an orphan reference."
            )
        if users_by_id[complaint.citizen_id].role != "CITIZEN":
            raise RuntimeError(
                f"Complaint {complaint.complaint_id} references a non-citizen user."
            )
        if citizen_ward.get(complaint.citizen_id) != ward_by_area.get(
            complaint.area_id
        ):
            raise RuntimeError(
                f"Complaint {complaint.complaint_id} is outside its citizen's "
                "mapped home ward."
            )

    vehicle_ids = {vehicle.vehicle_id for vehicle in vehicles}
    if any(location.vehicle_id not in vehicle_ids for location in gps):
        raise RuntimeError("A GPS record references a missing vehicle.")
    for location in gps:
        vehicle = vehicles_by_id[location.vehicle_id]
        worker = workers_by_id[vehicle.worker_id]
        area = areas_by_id[worker.assigned_area]
        point = Point(float(location.longitude), float(location.latitude))
        if not area_geometries[area.area_id].covers(point):
            raise RuntimeError(
                f"GPS record {location.location_id} is outside its vehicle area."
            )
        if not ward_geometries[area.ward_id].covers(point):
            raise RuntimeError(
                f"GPS record {location.location_id} is outside its municipal ward."
            )

    team_member_worker_ids = {member.worker_id for member in team_members}
    if len(team_member_worker_ids) != len(team_members):
        raise RuntimeError("A generated worker belongs to multiple active teams.")
    if team_member_worker_ids != set(workers_by_id):
        raise RuntimeError(
            "Every generated worker must belong to exactly one active team."
        )
    teams_by_id = {team.team_id: team for team in teams}
    for team in teams:
        if team.area_id not in areas_by_id or team.leader_worker_id not in workers_by_id:
            raise RuntimeError(f"Team {team.team_id} has an invalid area or leader.")
        if workers_by_id[team.leader_worker_id].assigned_area != team.area_id:
            raise RuntimeError(
                f"Team {team.team_id} area does not match its leader's assignment."
            )
        if team.vehicle_id is not None and team.vehicle_id not in vehicles_by_id:
            raise RuntimeError(f"Team {team.team_id} has an invalid vehicle.")
    for member in team_members:
        if (
            member.team_id not in teams_by_id
            or member.worker_id not in workers_by_id
            or teams_by_id[member.team_id].leader_worker_id != member.worker_id
        ):
            raise RuntimeError("A team member has an invalid team/worker assignment.")

    registered_alert_areas = set(areas_by_id)
    if any(alert.area_id not in registered_alert_areas for alert in rows["alerts"]):
        raise RuntimeError("A generated alert references a missing area.")


def ward_report(
    rows: dict[str, list],
    wards: list[MunicipalWard],
    demand_by_ward: dict[int, float],
) -> None:
    ward_by_id = {ward.ward_id: ward for ward in wards}
    all_areas = {area.area_id: area for area in rows.get("all_areas", [])}
    ward_by_id = {ward.ward_id: ward for ward in wards}
    reports_by_ward: dict[int, list[WasteReport]] = defaultdict(list)
    ward_by_area = {
        area.area_id: area.ward_id
        for area in all_areas.values()
        if area.ward_id is not None
    }
    for report in rows["waste_reports"]:
        ward_id = ward_by_area.get(report.area_id)
        if ward_id is not None:
            reports_by_ward[ward_id].append(report)

    requests_by_ward: dict[int, list[CollectionRequest]] = defaultdict(list)
    reports_by_id = {
        report.report_id: report for report in rows["waste_reports"]
    }
    for request in rows["collection_requests"]:
        report = reports_by_id.get(request.report_id)
        if report is not None and report.area_id in ward_by_area:
            requests_by_ward[ward_by_area[report.area_id]].append(request)

    ratings_by_ward: dict[int, list[SegregationRating]] = defaultdict(list)
    request_by_id = {
        request.request_id: request for request in rows["collection_requests"]
    }
    for rating in rows["segregation_ratings"]:
        request = request_by_id.get(rating.request_id)
        report = reports_by_id.get(request.report_id) if request else None
        if report is not None and report.area_id in ward_by_area:
            ratings_by_ward[ward_by_area[report.area_id]].append(rating)
    complaints_by_ward: Counter[int] = Counter(
        ward_by_area[complaint.area_id]
        for complaint in rows["complaints"]
        if complaint.area_id in ward_by_area
    )

    total_reports = len(rows["waste_reports"])
    total_waste = sum(float(report.quantity_kg) for report in rows["waste_reports"])
    date_values = [report.reported_at for report in rows["waste_reports"]]
    history_days = (
        max((max(date_values) - min(date_values)).total_seconds() / 86400, 1)
        if len(date_values) > 1
        else 1
    )
    print()
    print("Ward | Name | Population | Reports | Total Waste KG | Avg KG/Report")
    for ward in sorted(wards, key=lambda item: int(item.ward_number)):
        ward_reports = reports_by_ward.get(ward.ward_id, [])
        total_kg = sum(float(report.quantity_kg) for report in ward_reports)
        average = total_kg / len(ward_reports) if ward_reports else 0
        population = "NULL" if ward.population is None else str(ward.population)
        print(
            f"{ward.ward_number} | {ward.ward_name} | {population} | "
            f"{len(ward_reports)} | {total_kg:.2f} | {average:.2f}"
        )
    print()
    print("Waste type distribution by ward (reports):")
    for ward in sorted(wards, key=lambda item: int(item.ward_number)):
        distribution = Counter(
            report.waste_type for report in reports_by_ward.get(ward.ward_id, [])
        )
        print(
            f"Ward {ward.ward_number}: "
            + ", ".join(
                f"{waste_type}={distribution[waste_type]}"
                for waste_type in WASTE_TYPES
            )
        )

    waste_by_ward = {
        ward.ward_id: sum(
            float(report.quantity_kg)
            for report in reports_by_ward.get(ward.ward_id, [])
        )
        for ward in wards
    }
    if waste_by_ward:
        highest = max(waste_by_ward, key=waste_by_ward.get)
        lowest = min(waste_by_ward, key=waste_by_ward.get)
        print(
            f"Highest waste ward: {ward_by_id[highest].ward_number} - "
            f"{ward_by_id[highest].ward_name} ({waste_by_ward[highest]:.2f} kg)"
        )
        print(
            f"Lowest waste ward: {ward_by_id[lowest].ward_number} - "
            f"{ward_by_id[lowest].ward_name} ({waste_by_ward[lowest]:.2f} kg)"
        )
    collected = sum(
        request.status == "COLLECTED" for request in rows["collection_requests"]
    )
    efficiency = (
        100 * collected / len(rows["collection_requests"])
        if rows["collection_requests"]
        else 0
    )
    good_ratings = sum(rating.rating in (4, 5) for rating in rows["segregation_ratings"])
    segregation_rate = (
        100 * good_ratings / len(rows["segregation_ratings"])
        if rows["segregation_ratings"]
        else 0
    )
    average_rating = (
        sum(rating.rating for rating in rows["segregation_ratings"])
        / len(rows["segregation_ratings"])
        if rows["segregation_ratings"]
        else 0
    )
    staffed_area_ids = {worker.assigned_area for worker in rows["workers"]}
    staffed_reports = [
        report
        for report in rows["waste_reports"]
        if report.area_id in staffed_area_ids
    ]
    staffed_report_ids = {report.report_id for report in staffed_reports}
    staffed_report_requests = sum(
        request.report_id in staffed_report_ids
        for request in rows["collection_requests"]
    )
    staffed_request_rate = (
        100 * staffed_report_requests / len(staffed_reports)
        if staffed_reports
        else 0
    )
    print(f"Total generated waste: {total_waste:.2f} kg")
    print(f"Approximate overall daily demand (observed): {total_waste / history_days:.2f} kg/day")
    print(f"Approximate overall weekly demand (observed): {total_waste * 7 / history_days:.2f} kg/week")
    print(f"Overall collection efficiency: {efficiency:.2f}%")
    print(f"Overall segregation rate (ratings 4-5): {segregation_rate:.2f}%")
    print(f"Average segregation rating: {average_rating:.2f}/5")
    print("Ward-level operational performance:")
    for ward in sorted(wards, key=lambda item: int(item.ward_number)):
        ward_requests = requests_by_ward.get(ward.ward_id, [])
        ward_collected = sum(
            request.status == "COLLECTED" for request in ward_requests
        )
        collection_efficiency = (
            100 * ward_collected / len(ward_requests) if ward_requests else 0
        )
        ward_ratings = ratings_by_ward.get(ward.ward_id, [])
        ward_good = sum(rating.rating in (4, 5) for rating in ward_ratings)
        ward_segregation_rate = (
            100 * ward_good / len(ward_ratings) if ward_ratings else 0
        )
        ward_average = (
            sum(rating.rating for rating in ward_ratings) / len(ward_ratings)
            if ward_ratings
            else 0
        )
        print(
            f"Ward {ward.ward_number}: requests={len(ward_requests)}, "
            f"collected={ward_collected}, collection efficiency="
            f"{collection_efficiency:.2f}%, ratings={len(ward_ratings)}, "
            f"good segregation={ward_segregation_rate:.2f}%, "
            f"average rating={ward_average:.2f}/5, "
            f"complaints={complaints_by_ward[ward.ward_id]}"
        )
    print(
        "Collection request coverage: "
        f"{len(rows['collection_requests'])}/{total_reports} reports overall; "
        f"{staffed_report_requests}/{len(staffed_reports)} staffed-area reports "
        f"({staffed_request_rate:.2f}%)."
    )
    print("Approximate daily/weekly observed waste demand by ward:")
    for ward in sorted(wards, key=lambda item: int(item.ward_number)):
        ward_reports = reports_by_ward.get(ward.ward_id, [])
        kg = sum(float(report.quantity_kg) for report in ward_reports)
        print(
            f"Ward {ward.ward_number}: {kg / history_days:.2f} kg/day, "
            f"{kg * 7 / history_days:.2f} kg/week; "
            f"demand prior {demand_by_ward.get(ward.ward_id, 0):.2f} kg/day"
        )


def print_summary(
    rows: dict[str, list],
    wards: list[MunicipalWard],
    demand_by_ward: dict[int, float],
) -> None:
    requests = rows["collection_requests"]
    collected = sum(request.status == "COLLECTED" for request in requests)
    print("====================================")
    print("BHOPAL DEVELOPMENT DATA SEED")
    print("====================================")
    print(f"Citizens: {sum(user.role == 'CITIZEN' for user in rows['users'])}")
    print(f"Workers: {len(rows['workers'])}")
    print(f"Waste reports: {len(rows['waste_reports'])}")
    print(f"Collection requests: {len(requests)}")
    print(f"Collected: {collected}")
    print(f"Segregation ratings: {len(rows['segregation_ratings'])}")
    print(f"Rewards: {len(rows['reward_transactions'])}")
    print(f"Penalties: {len(rows['penalties'])}")
    print(f"Complaints: {len(rows['complaints'])}")
    print(f"Vehicles: {len(rows['vehicles'])}")
    print(f"GPS records: {len(rows['vehicle_locations'])}")
    print(f"Alerts: {len(rows['alerts'])}")
    print(f"Provisional operational areas created: {len(rows['areas'])}")
    print_summary_rows = dict(rows)
    print_summary_rows["all_areas"] = rows.get("all_areas", [])
    ward_report(print_summary_rows, wards, demand_by_ward)


def demand_for_reporting(
    wards: list[MunicipalWard],
    rng: random.Random,
) -> dict[int, float]:
    return build_demand_weights(rng, wards)


def reset_generated(db: Session) -> None:
    manifest = load_manifest(db)
    if not any(manifest.values()):
        print("No registered Bhopal development seed records to remove.")
        return

    ids = {table: set(values) for table, values in manifest.items()}
    safety_checks = (
        ("workers", "user_id", "users", "user_id"),
        ("waste_reports", "citizen_id", "users", "user_id"),
        ("complaints", "citizen_id", "users", "user_id"),
        ("segregation_ratings", "citizen_id", "users", "user_id"),
        ("reward_transactions", "citizen_id", "users", "user_id"),
        ("penalties", "citizen_id", "users", "user_id"),
        ("workers", "assigned_area", "areas", "area_id"),
        ("waste_reports", "area_id", "areas", "area_id"),
        ("complaints", "area_id", "areas", "area_id"),
        ("alerts", "area_id", "areas", "area_id"),
        ("teams", "area_id", "areas", "area_id"),
        ("collection_requests", "worker_id", "workers", "worker_id"),
        ("segregation_ratings", "worker_id", "workers", "worker_id"),
        ("vehicles", "worker_id", "workers", "worker_id"),
        ("teams", "leader_worker_id", "workers", "worker_id"),
        ("team_members", "worker_id", "workers", "worker_id"),
        ("vehicle_locations", "vehicle_id", "vehicles", "vehicle_id"),
        ("teams", "vehicle_id", "vehicles", "vehicle_id"),
        ("collection_requests", "report_id", "waste_reports", "report_id"),
        ("segregation_ratings", "request_id", "collection_requests", "request_id"),
        ("reward_transactions", "reference_id", "segregation_ratings", "rating_id"),
    )
    for source_table, source_column, target_table, _ in safety_checks:
        target_ids = ids.get(target_table, set())
        if not target_ids:
            continue
        model, _ = TABLE_MODELS[source_table]
        query = db.query(model).filter(
            getattr(model, source_column).in_(target_ids)
        )
        source_id_column = TABLE_MODELS[source_table][1]
        registered_source_ids = ids.get(source_table, set())
        if registered_source_ids:
            query = query.filter(
                getattr(model, source_id_column).notin_(registered_source_ids)
            )
        if query.first() is not None:
            raise RuntimeError(
                f"Cannot reset generated {target_table}: non-seed application "
                f"data in {source_table} references it. Remove or reassign that "
                "dependent data first."
            )

    db.execute(
        text(
            f"DELETE FROM {SEED_CITIZEN_WARD_TABLE} "
            "WHERE seed_name = :seed_name"
        ),
        {"seed_name": SEED_NAME},
    )
    for table_name in RESET_ORDER:
        target_ids = ids.get(table_name, set())
        if not target_ids:
            continue
        model, id_field = TABLE_MODELS[table_name]
        db.query(model).filter(getattr(model, id_field).in_(target_ids)).delete(
            synchronize_session=False
        )
    db.execute(
        text(
            "DELETE FROM development_seed_records WHERE seed_name = :seed_name"
        ),
        {"seed_name": SEED_NAME},
    )
    db.commit()
    print(
        "Generated Bhopal development data removed. Municipal wards, their "
        "geometry, pre-existing areas, and non-seed application records preserved."
    )


def run_seed(db: Session, args: argparse.Namespace) -> None:
    ensure_registry(db)
    manifest = load_manifest(db)
    wards = db.query(MunicipalWard).order_by(MunicipalWard.ward_id).all()
    if len(wards) != 85:
        raise RuntimeError(
            f"Expected the preserved 85 municipal wards, found {len(wards)}. "
            "No generated records have been changed."
        )
    if any(ward.ward_number == "44" and ward.population is not None for ward in wards):
        raise RuntimeError("Ward 44 population must remain NULL.")

    rng = random.Random(args.seed)
    demand_by_ward = demand_for_reporting(wards, rng)
    if not any(manifest.values()):
        if args.reports != REPORT_COUNT:
            raise RuntimeError(
                f"A clean development seed must create exactly {REPORT_COUNT} "
                "reports; no seed data has been committed."
            )
        areas_by_ward, new_area_count = create_provisional_areas(db, wards)
        if any(not areas_by_ward.get(ward.ward_id) for ward in wards):
            raise RuntimeError("At least one municipal ward has no operational area.")
        if new_area_count != len(load_manifest(db).get("areas", [])):
            raise RuntimeError(
                "Provisional area creation did not cover each ward."
            )
        all_areas = db.query(Area).order_by(Area.area_id).all()
        ward_geometries = get_ward_geometries(wards)
        area_geometries = get_area_geometries(all_areas, ward_geometries)
        citizens, workers, worker_area_by_id = create_users_and_workers(
            db,
            rng,
            wards,
            areas_by_ward,
            demand_by_ward,
            args.citizens,
            args.workers,
        )
        reports = create_reports(
            db,
            rng,
            wards,
            areas_by_ward,
            ward_geometries,
            area_geometries,
            citizens,
            demand_by_ward,
            args.reports,
        )
        citizen_ward = persist_citizen_wards(
            db,
            citizens,
            reports,
            {
                area.area_id: area.ward_id
                for area in all_areas
                if area.ward_id is not None
            },
            demand_by_ward,
            random.Random(args.seed),
        )
        requests = create_collections(db, rng, reports, workers)
        reports_by_id = {report.report_id: report for report in reports}
        ratings, rewards, _ = create_ratings_and_incentives(
            db,
            rng,
            reports_by_id,
            requests,
        )
        citizens_by_ward = align_generated_citizen_references(
            random.Random(args.seed + 1),
            citizens,
            citizen_ward,
            reports,
            requests,
            ratings,
            rewards,
            [],
            {
                area.area_id: area.ward_id
                for area in all_areas
                if area.ward_id is not None
            },
        )
        complaints = create_complaints(
            db,
            random.Random(args.seed + 2),
            citizens_by_ward,
            wards,
            areas_by_ward,
            demand_by_ward,
            args.complaints,
        )
        create_vehicles_teams_and_gps(
            db,
            rng,
            workers,
            worker_area_by_id,
            area_geometries,
            args.vehicles,
            args.gps,
        )
        create_alerts(db, reports, complaints, areas_by_ward)
    else:
        rows = rows_from_manifest(db, manifest)
        citizens = [user for user in rows["users"] if user.role == "CITIZEN"]
        workers = rows["workers"]
        if len(rows["waste_reports"]) != args.reports:
            raise RuntimeError(
                f"The registered seed contains {len(rows['waste_reports'])} "
                f"reports; expected {args.reports}. The seeder will not delete, "
                "replace, or append waste reports."
            )
        citizens = add_missing_citizens(
            db,
            random.Random(args.seed + 10),
            citizens,
            args.citizens,
        )
        if db.query(User).filter(User.role == "CITIZEN").count() != args.citizens:
            raise RuntimeError(
                "The total citizen count includes non-seed records or does not "
                "match the requested target; refusing to alter unrelated users."
            )
        if db.query(Worker).count() > args.workers:
            raise RuntimeError(
                "The total worker count exceeds the requested target; refusing "
                "to delete or alter unrelated workers."
            )

        all_areas = db.query(Area).order_by(Area.area_id).all()
        reports = rows["waste_reports"]
        requests = rows["collection_requests"]
        area_ward = {
            area.area_id: area.ward_id
            for area in all_areas
            if area.ward_id is not None
        }
        citizen_ward = persist_citizen_wards(
            db,
            citizens,
            reports,
            area_ward,
            demand_by_ward,
            random.Random(args.seed),
        )
        workers, _, newly_staffed_area_ids = add_missing_workers(
            db,
            random.Random(args.seed + 20),
            workers,
            args.workers,
            all_areas,
            demand_by_ward,
            reports,
            requests,
        )
        if db.query(Worker).count() != args.workers:
            raise RuntimeError(
                "The total worker count includes non-seed records or does not "
                "match the requested target; refusing to alter unrelated workers."
            )
        new_requests = create_collections_for_newly_staffed_areas(
            db,
            random.Random(args.seed + 30),
            reports,
            workers,
            newly_staffed_area_ids,
            requests,
        )
        create_ratings_and_incentives(
            db,
            random.Random(args.seed + 40),
            {report.report_id: report for report in reports},
            new_requests,
        )
        manifest = load_manifest(db)
        rows = rows_from_manifest(db, manifest)
        citizens = [user for user in rows["users"] if user.role == "CITIZEN"]
        citizen_ward = {
            int(citizen_id): int(ward_id)
            for citizen_id, ward_id in db.execute(
                text(
                    f"""
                    SELECT citizen_id, ward_id
                    FROM {SEED_CITIZEN_WARD_TABLE}
                    WHERE seed_name = :seed_name
                    """
                ),
                {"seed_name": SEED_NAME},
            ).all()
        }
        align_generated_citizen_references(
            random.Random(args.seed + 50),
            citizens,
            citizen_ward,
            rows["waste_reports"],
            rows["collection_requests"],
            rows["segregation_ratings"],
            rows["reward_transactions"],
            rows["complaints"],
            area_ward,
        )

    rows = rows_from_manifest(db, load_manifest(db))
    rows["all_areas"] = all_areas
    citizens = [user for user in rows["users"] if user.role == "CITIZEN"]
    persisted_mapping = {
        int(citizen_id): int(ward_id)
        for citizen_id, ward_id in db.execute(
            text(
                f"""
                SELECT citizen_id, ward_id
                FROM {SEED_CITIZEN_WARD_TABLE}
                WHERE seed_name = :seed_name
                """
            ),
            {"seed_name": SEED_NAME},
        ).all()
    }
    if persisted_mapping != citizen_ward:
        raise RuntimeError(
            "Persisted citizen-to-ward mapping does not match generated users."
        )
    if len(rows["waste_reports"]) != args.reports:
        raise RuntimeError(
            f"Expected exactly {args.reports} waste reports, found "
            f"{len(rows['waste_reports'])}."
        )
    if len(citizens) != args.citizens or len(rows["workers"]) != args.workers:
        raise RuntimeError(
            "Final generated citizen/worker counts do not match the requested "
            "targets."
        )
    validate_seed(rows, wards, all_areas, citizen_ward)
    db.commit()

    print(
        f"Baseline daily waste is {DAILY_WASTE_PER_PERSON_KG} kg/person/day "
        "for development demand weighting only; population records were not changed."
    )
    print(
        "Ward 44 uses a neutral median-known-population demand weight only; "
        "its stored population remains NULL."
    )
    print(
        "Worker allocation preserves existing assignments and adds staff only "
        "to unstaffed report-bearing areas ranked by demand, waste volume, and "
        "unassigned collection workload."
    )
    print_summary(rows, wards, demand_by_ward)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed controlled, polygon-validated Bhopal development data."
    )
    parser.add_argument("--citizens", type=int, default=CITIZEN_COUNT)
    parser.add_argument("--workers", type=int, default=WORKER_COUNT)
    parser.add_argument("--reports", type=int, default=REPORT_COUNT)
    parser.add_argument("--complaints", type=int, default=COMPLAINT_COUNT)
    parser.add_argument("--vehicles", type=int, default=VEHICLE_COUNT)
    parser.add_argument("--gps", type=int, default=GPS_COUNT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--reset-generated", action="store_true")
    parser.add_argument(
        "--ensure-operations-account",
        action="store_true",
        help="Create an ADMIN/MONITOR account from environment variables only.",
    )
    args = parser.parse_args()
    if args.reset_generated and args.ensure_operations_account:
        parser.error("--reset-generated cannot be combined with --ensure-operations-account.")
    if min(
        args.citizens,
        args.workers,
        args.reports,
        args.complaints,
        args.vehicles,
        args.gps,
    ) < 1:
        parser.error("All generated record counts must be at least 1.")
    if args.gps % args.vehicles != 0:
        parser.error("--gps must divide evenly among --vehicles.")
    if args.workers > 85:
        parser.error("--workers cannot exceed the 85 municipal ward areas.")
    return args


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    db = SessionLocal()
    try:
        if args.reset_generated:
            reset_generated(db)
            return
        if args.ensure_operations_account:
            ensure_development_operations_account(db)
            return
        run_seed(db, args)
        ensure_development_operations_account(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
