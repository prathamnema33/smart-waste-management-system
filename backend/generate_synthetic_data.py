# generate_synthetic_data.py

import random
from datetime import datetime, timedelta
from decimal import Decimal

from faker import Faker
from passlib.context import CryptContext
from sqlalchemy import text

from database import engine


# ============================================================
# CONFIGURATION
# ============================================================

NUM_CITIZENS = 1000
NUM_WORKERS = 50
NUM_AREAS = 20
NUM_REPORTS = 20000
NUM_COMPLAINTS = 4000
NUM_VEHICLES = 50
NUM_GPS_RECORDS = 50000
NUM_REWARDS = 8000
NUM_PENALTIES = 2000
NUM_ALERTS = 500

RANDOM_SEED = 42

fake = Faker("en_IN")
Faker.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)


# ============================================================
# PASSWORD HASHING
# ============================================================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# Development password for all generated users
SYNTHETIC_PASSWORD = "Synthetic123!"

password_hash = pwd_context.hash(SYNTHETIC_PASSWORD)


# ============================================================
# CONSTANTS
# ============================================================

WASTE_TYPES = [
    "Organic",
    "Plastic",
    "Paper",
    "Glass",
    "Metal",
    "E-Waste",
]

PRIORITIES = [
    "LOW",
    "MEDIUM",
    "HIGH",
]

WASTE_STATUSES = [
    "PENDING",
    "ASSIGNED",
    "COLLECTED",
]

COLLECTION_STATUSES = [
    "ASSIGNED",
    "COLLECTED",
]

COMPLAINT_CATEGORIES = [
    "MISSED_COLLECTION",
    "ILLEGAL_DUMPING",
    "OVERFLOWING_BIN",
    "SEGREGATION",
    "OTHER",
]

COMPLAINT_PRIORITIES = [
    "LOW",
    "MEDIUM",
    "HIGH",
]

COMPLAINT_STATUSES = [
    "OPEN",
    "IN_PROGRESS",
    "RESOLVED",
]

VEHICLE_STATUSES = [
    "ACTIVE",
    "INACTIVE",
]

ALERT_TYPES = [
    "MISSED_COLLECTION",
    "HIGH_WASTE",
    "ILLEGAL_DUMPING",
    "OVERFLOWING_BIN",
]

ALERT_SEVERITIES = [
    "LOW",
    "MEDIUM",
    "HIGH",
]

ALERT_STATUSES = [
    "OPEN",
    "RESOLVED",
]

REWARD_TYPES = [
    "EARNED",
    "REDEEMED",
]

REWARD_POINTS = [
    5,
    10,
    20,
    25,
    50,
]

PENALTY_STATUSES = [
    "PENDING",
    "PAID",
]


# ============================================================
# HELPERS
# ============================================================

def random_datetime(days_back=365):
    """
    Generate random datetime between now and given days in past.
    """
    now = datetime.now()

    start = now - timedelta(days=days_back)

    random_seconds = random.randint(
        0,
        int((now - start).total_seconds())
    )

    return start + timedelta(seconds=random_seconds)


def random_future_or_past_datetime(base_datetime, max_days=3):
    """
    Generate datetime after a given datetime.
    """
    return base_datetime + timedelta(
        minutes=random.randint(10, max_days * 24 * 60)
    )


def random_quantity():
    """
    Generate realistic waste quantity.
    """
    return round(
        random.uniform(0.5, 25.0),
        2
    )


def random_coordinates(area_index):
    """
    Generate coordinates around Bhopal region.

    These are synthetic coordinates only.
    """

    base_lat = 23.2599
    base_lon = 77.4126

    lat_offset = random.uniform(-0.08, 0.08)
    lon_offset = random.uniform(-0.08, 0.08)

    return (
        round(base_lat + lat_offset, 6),
        round(base_lon + lon_offset, 6)
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("SMART WASTE MANAGEMENT")
    print("SYNTHETIC DATA GENERATOR")
    print("=" * 70)

    print("\nConfiguration:")
    print(f"Citizens       : {NUM_CITIZENS}")
    print(f"Workers        : {NUM_WORKERS}")
    print(f"Areas          : {NUM_AREAS}")
    print(f"Waste Reports  : {NUM_REPORTS}")
    print(f"Complaints     : {NUM_COMPLAINTS}")
    print(f"Vehicles       : {NUM_VEHICLES}")
    print(f"GPS Records    : {NUM_GPS_RECORDS}")
    print(f"Rewards        : {NUM_REWARDS}")
    print(f"Penalties      : {NUM_PENALTIES}")
    print(f"Alerts         : {NUM_ALERTS}")

    print("\nSynthetic user password:")
    print(SYNTHETIC_PASSWORD)

    print("\nConnecting to database...")

    with engine.begin() as conn:

        # ====================================================
        # EXISTING USERS
        # ====================================================

        existing_citizens = conn.execute(
            text("""
                SELECT user_id
                FROM users
                WHERE UPPER(role) = 'CITIZEN'
            """)
        ).fetchall()

        citizen_ids = [
            row[0]
            for row in existing_citizens
        ]

        print(
            f"\nExisting citizens found: "
            f"{len(citizen_ids)}"
        )


        # ====================================================
        # EXISTING WORKERS
        # ====================================================

        existing_workers = conn.execute(
            text("""
                SELECT worker_id
                FROM workers
            """)
        ).fetchall()

        worker_ids = [
            row[0]
            for row in existing_workers
        ]

        print(
            f"Existing workers found: "
            f"{len(worker_ids)}"
        )


        # ====================================================
        # AREAS
        # ====================================================

        print("\nCreating areas...")

        area_ids = []

        for i in range(1, NUM_AREAS + 1):

            area_name = f"Synthetic Zone {i}"

            lat, lon = random_coordinates(i)

            result = conn.execute(
                text("""
                    INSERT INTO areas (
                        area_name,
                        latitude,
                        longitude
                    )
                    VALUES (
                        :area_name,
                        :latitude,
                        :longitude
                    )
                    RETURNING area_id
                """),
                {
                    "area_name": area_name,
                    "latitude": lat,
                    "longitude": lon,
                }
            )

            area_ids.append(
                result.scalar()
            )

        print(
            f"New areas created: {len(area_ids)}"
        )


        # ====================================================
        # CITIZENS
        # ====================================================

        print("\nCreating citizens...")

        new_citizen_ids = []

        for i in range(NUM_CITIZENS):

            name = fake.name()

            email = (
                f"citizen_{random.randint(100000, 999999999)}"
                f"_{i}@example.com"
            )

            result = conn.execute(
                text("""
                    INSERT INTO users (
                        name,
                        email,
                        password_hash,
                        role,
                        created_at
                    )
                    VALUES (
                        :name,
                        :email,
                        :password_hash,
                        'CITIZEN',
                        :created_at
                    )
                    RETURNING user_id
                """),
                {
                    "name": name,
                    "email": email,
                    "password_hash": password_hash,
                    "created_at": random_datetime(365),
                }
            )

            new_citizen_ids.append(
                result.scalar()
            )

        citizen_ids.extend(new_citizen_ids)

        print(
            f"New citizens created: "
            f"{len(new_citizen_ids)}"
        )


        # ====================================================
        # WORKERS
        # ====================================================

        print("\nCreating workers...")

        new_worker_ids = []

        for i in range(NUM_WORKERS):

            name = fake.name()

            email = (
                f"worker_{random.randint(100000, 999999999)}"
                f"_{i}@example.com"
            )

            result = conn.execute(
                text("""
                    INSERT INTO users (
                        name,
                        email,
                        password_hash,
                        role,
                        created_at
                    )
                    VALUES (
                        :name,
                        :email,
                        :password_hash,
                        'WORKER',
                        :created_at
                    )
                    RETURNING user_id
                """),
                {
                    "name": name,
                    "email": email,
                    "password_hash": password_hash,
                    "created_at": random_datetime(365),
                }
            )

            user_id = result.scalar()

            area_id = random.choice(area_ids)

            result = conn.execute(
                text("""
                    INSERT INTO workers (
                        user_id,
                        assigned_area
                    )
                    VALUES (
                        :user_id,
                        :assigned_area
                    )
                    RETURNING worker_id
                """),
                {
                    "user_id": user_id,
                    "assigned_area": area_id,
                }
            )

            worker_id = result.scalar()

            new_worker_ids.append(
                worker_id
            )

        worker_ids.extend(new_worker_ids)

        print(
            f"New workers created: "
            f"{len(new_worker_ids)}"
        )


        # ====================================================
        # WASTE REPORTS
        # ====================================================

        print("\nCreating waste reports...")

        report_ids = []

        for i in range(NUM_REPORTS):

            citizen_id = random.choice(
                citizen_ids
            )

            area_id = random.choice(
                area_ids
            )

            waste_type = random.choice(
                WASTE_TYPES
            )

            quantity = random_quantity()

            latitude, longitude = random_coordinates(
                area_id
            )

            priority = random.choices(
                PRIORITIES,
                weights=[60, 30, 10]
            )[0]

            status = random.choices(
                WASTE_STATUSES,
                weights=[10, 10, 80]
            )[0]

            reported_at = random_datetime(365)

            result = conn.execute(
                text("""
                    INSERT INTO waste_reports (
                        citizen_id,
                        area_id,
                        waste_type,
                        quantity_kg,
                        latitude,
                        longitude,
                        priority,
                        status,
                        reported_at
                    )
                    VALUES (
                        :citizen_id,
                        :area_id,
                        :waste_type,
                        :quantity_kg,
                        :latitude,
                        :longitude,
                        :priority,
                        :status,
                        :reported_at
                    )
                    RETURNING report_id
                """),
                {
                    "citizen_id": citizen_id,
                    "area_id": area_id,
                    "waste_type": waste_type,
                    "quantity_kg": quantity,
                    "latitude": latitude,
                    "longitude": longitude,
                    "priority": priority,
                    "status": status,
                    "reported_at": reported_at,
                }
            )

            report_ids.append(
                result.scalar()
            )

            if (i + 1) % 5000 == 0:
                print(
                    f"  Reports created: {i + 1}"
                )

        print(
            f"Total new waste reports: "
            f"{len(report_ids)}"
        )


        # ====================================================
        # COLLECTION REQUESTS
        # ====================================================

        print("\nCreating collection requests...")

        collection_ids = []

        # Around 80% reports get collection requests
        number_of_collections = int(
            NUM_REPORTS * 0.80
        )

        selected_reports = random.sample(
            report_ids,
            number_of_collections
        )

        for report_id in selected_reports:

            worker_id = random.choice(
                worker_ids
            )

            assigned_at = random_datetime(180)

            status = random.choices(
                COLLECTION_STATUSES,
                weights=[20, 80]
            )[0]

            collected_at = None

            if status == "COLLECTED":

                collected_at = (
                    assigned_at
                    + timedelta(
                        minutes=random.randint(
                            20,
                            240
                        )
                    )
                )

            result = conn.execute(
                text("""
                    INSERT INTO collection_requests (
                        report_id,
                        worker_id,
                        assigned_at,
                        collected_at,
                        status
                    )
                    VALUES (
                        :report_id,
                        :worker_id,
                        :assigned_at,
                        :collected_at,
                        :status
                    )
                    RETURNING request_id
                """),
                {
                    "report_id": report_id,
                    "worker_id": worker_id,
                    "assigned_at": assigned_at,
                    "collected_at": collected_at,
                    "status": status,
                }
            )

            collection_ids.append(
                result.scalar()
            )

        print(
            f"Collection requests created: "
            f"{len(collection_ids)}"
        )


        # ====================================================
        # SEGREGATION RATINGS
        # ====================================================

        print("\nCreating segregation ratings...")

        rating_ids = []

        # Around 75% collection requests get ratings
        number_of_ratings = int(
            len(collection_ids) * 0.75
        )

        selected_collections = random.sample(
            collection_ids,
            number_of_ratings
        )

        # Get collection details
        collection_details = {}

        result = conn.execute(
            text("""
                SELECT
                    cr.request_id,
                    cr.worker_id,
                    wr.citizen_id
                FROM collection_requests cr
                JOIN waste_reports wr
                    ON cr.report_id = wr.report_id
                WHERE cr.request_id = ANY(:ids)
            """),
            {
                "ids": selected_collections
            }
        )

        for row in result:

            collection_details[
                row[0]
            ] = {
                "worker_id": row[1],
                "citizen_id": row[2],
            }

        for request_id in selected_collections:

            details = collection_details.get(
                request_id
            )

            if not details:
                continue

            rating = random.choices(
                [1, 2, 3, 4, 5],
                weights=[
                    3,
                    7,
                    15,
                    35,
                    40
                ]
            )[0]

            remarks = random.choice([
                "Good segregation",
                "Properly segregated",
                "Needs improvement",
                "Mixed waste found",
                "Excellent segregation",
                None,
            ])

            rated_at = random_datetime(180)

            result = conn.execute(
                text("""
                    INSERT INTO segregation_ratings (
                        request_id,
                        citizen_id,
                        worker_id,
                        rating,
                        remarks,
                        rated_at
                    )
                    VALUES (
                        :request_id,
                        :citizen_id,
                        :worker_id,
                        :rating,
                        :remarks,
                        :rated_at
                    )
                    RETURNING rating_id
                """),
                {
                    "request_id": request_id,
                    "citizen_id": details["citizen_id"],
                    "worker_id": details["worker_id"],
                    "rating": rating,
                    "remarks": remarks,
                    "rated_at": rated_at,
                }
            )

            rating_ids.append(
                result.scalar()
            )

        print(
            f"Segregation ratings created: "
            f"{len(rating_ids)}"
        )


        # ====================================================
        # COMPLAINTS
        # ====================================================

        print("\nCreating complaints...")

        complaint_ids = []

        for i in range(NUM_COMPLAINTS):

            citizen_id = random.choice(
                citizen_ids
            )

            area_id = random.choice(
                area_ids
            )

            category = random.choice(
                COMPLAINT_CATEGORIES
            )

            descriptions = {
                "MISSED_COLLECTION":
                    "Waste collection was missed.",
                "ILLEGAL_DUMPING":
                    "Illegal dumping observed in the area.",
                "OVERFLOWING_BIN":
                    "Garbage bin is overflowing.",
                "SEGREGATION":
                    "Waste segregation issue reported.",
                "OTHER":
                    "General waste management complaint.",
            }

            description = descriptions[
                category
            ]

            priority = random.choices(
                COMPLAINT_PRIORITIES,
                weights=[50, 35, 15]
            )[0]

            status = random.choices(
                COMPLAINT_STATUSES,
                weights=[25, 20, 55]
            )[0]

            created_at = random_datetime(365)

            resolved_at = None

            if status == "RESOLVED":

                resolved_at = (
                    created_at
                    + timedelta(
                        hours=random.randint(
                            2,
                            120
                        )
                    )
                )

            result = conn.execute(
                text("""
                    INSERT INTO complaints (
                        citizen_id,
                        area_id,
                        category,
                        description,
                        priority,
                        status,
                        created_at,
                        resolved_at
                    )
                    VALUES (
                        :citizen_id,
                        :area_id,
                        :category,
                        :description,
                        :priority,
                        :status,
                        :created_at,
                        :resolved_at
                    )
                    RETURNING complaint_id
                """),
                {
                    "citizen_id": citizen_id,
                    "area_id": area_id,
                    "category": category,
                    "description": description,
                    "priority": priority,
                    "status": status,
                    "created_at": created_at,
                    "resolved_at": resolved_at,
                }
            )

            complaint_ids.append(
                result.scalar()
            )

            if (i + 1) % 1000 == 0:
                print(
                    f"  Complaints created: "
                    f"{i + 1}"
                )

        print(
            f"Total complaints created: "
            f"{len(complaint_ids)}"
        )


        # ====================================================
        # REWARD TRANSACTIONS
        # ====================================================

        print("\nCreating reward transactions...")

        reward_ids = []

        for i in range(NUM_REWARDS):

            citizen_id = random.choice(
                citizen_ids
            )

            transaction_type = random.choice(
                REWARD_TYPES
            )

            points = random.choice(
                REWARD_POINTS
            )

            # Redeemed points should be positive as
            # transaction amount; business logic can
            # interpret transaction_type.

            reference_id = None

            created_at = random_datetime(365)

            result = conn.execute(
                text("""
                    INSERT INTO reward_transactions (
                        citizen_id,
                        points,
                        transaction_type,
                        reference_id,
                        created_at
                    )
                    VALUES (
                        :citizen_id,
                        :points,
                        :transaction_type,
                        :reference_id,
                        :created_at
                    )
                    RETURNING transaction_id
                """),
                {
                    "citizen_id": citizen_id,
                    "points": points,
                    "transaction_type": transaction_type,
                    "reference_id": reference_id,
                    "created_at": created_at,
                }
            )

            reward_ids.append(
                result.scalar()
            )

        print(
            f"Reward transactions created: "
            f"{len(reward_ids)}"
        )


        # ====================================================
        # PENALTIES
        # ====================================================

        print("\nCreating penalties...")

        penalty_ids = []

        for i in range(NUM_PENALTIES):

            citizen_id = random.choice(
                citizen_ids
            )

            reasons = [
                "Poor waste segregation",
                "Repeated segregation violation",
                "Improper disposal",
                "Mixed waste disposal",
                "Waste dumped outside designated area",
            ]

            reason = random.choice(
                reasons
            )

            amount = Decimal(
                random.choice([
                    50,
                    100,
                    150,
                    200,
                    250,
                    500,
                ])
            )

            status = random.choice(
                PENALTY_STATUSES
            )

            created_at = random_datetime(365)

            result = conn.execute(
                text("""
                    INSERT INTO penalties (
                        citizen_id,
                        reason,
                        amount,
                        status,
                        created_at
                    )
                    VALUES (
                        :citizen_id,
                        :reason,
                        :amount,
                        :status,
                        :created_at
                    )
                    RETURNING penalty_id
                """),
                {
                    "citizen_id": citizen_id,
                    "reason": reason,
                    "amount": amount,
                    "status": status,
                    "created_at": created_at,
                }
            )

            penalty_ids.append(
                result.scalar()
            )

        print(
            f"Penalties created: "
            f"{len(penalty_ids)}"
        )


        # ====================================================
        # VEHICLES
        # ====================================================

        print("\nCreating vehicles...")

        vehicle_ids = []

        for i in range(NUM_VEHICLES):

            vehicle_number = (
                f"MP04AB"
                f"{random.randint(1000, 9999)}"
            )

            worker_id = random.choice(
                worker_ids
            )

            status = random.choice(
                VEHICLE_STATUSES
            )

            result = conn.execute(
                text("""
                    INSERT INTO vehicles (
                        vehicle_number,
                        worker_id,
                        status
                    )
                    VALUES (
                        :vehicle_number,
                        :worker_id,
                        :status
                    )
                    RETURNING vehicle_id
                """),
                {
                    "vehicle_number": vehicle_number,
                    "worker_id": worker_id,
                    "status": status,
                }
            )

            vehicle_ids.append(
                result.scalar()
            )

        print(
            f"Vehicles created: "
            f"{len(vehicle_ids)}"
        )


        # ====================================================
        # GPS LOCATIONS
        # ====================================================

        print("\nCreating GPS records...")

        for i in range(NUM_GPS_RECORDS):

            vehicle_id = random.choice(
                vehicle_ids
            )

            latitude, longitude = random_coordinates(
                random.choice(area_ids)
            )

            recorded_at = random_datetime(
                30
            )

            conn.execute(
                text("""
                    INSERT INTO vehicle_locations (
                        vehicle_id,
                        latitude,
                        longitude,
                        recorded_at
                    )
                    VALUES (
                        :vehicle_id,
                        :latitude,
                        :longitude,
                        :recorded_at
                    )
                """),
                {
                    "vehicle_id": vehicle_id,
                    "latitude": latitude,
                    "longitude": longitude,
                    "recorded_at": recorded_at,
                }
            )

            if (i + 1) % 10000 == 0:
                print(
                    f"  GPS records created: "
                    f"{i + 1}"
                )

        print(
            f"GPS records created: "
            f"{NUM_GPS_RECORDS}"
        )


        # ====================================================
        # ALERTS
        # ====================================================

        print("\nCreating alerts...")

        alert_ids = []

        messages = {
            "MISSED_COLLECTION":
                "Waste collection has been missed in this area.",

            "HIGH_WASTE":
                "Waste generation is unusually high in this area.",

            "ILLEGAL_DUMPING":
                "Possible illegal dumping detected.",

            "OVERFLOWING_BIN":
                "Waste bin may be overflowing.",
        }

        for i in range(NUM_ALERTS):

            area_id = random.choice(
                area_ids
            )

            alert_type = random.choice(
                ALERT_TYPES
            )

            severity = random.choices(
                ALERT_SEVERITIES,
                weights=[50, 35, 15]
            )[0]

            message = messages[
                alert_type
            ]

            status = random.choices(
                ALERT_STATUSES,
                weights=[70, 30]
            )[0]

            created_at = random_datetime(
                180
            )

            result = conn.execute(
                text("""
                    INSERT INTO alerts (
                        area_id,
                        alert_type,
                        severity,
                        message,
                        created_at,
                        status
                    )
                    VALUES (
                        :area_id,
                        :alert_type,
                        :severity,
                        :message,
                        :created_at,
                        :status
                    )
                    RETURNING alert_id
                """),
                {
                    "area_id": area_id,
                    "alert_type": alert_type,
                    "severity": severity,
                    "message": message,
                    "created_at": created_at,
                    "status": status,
                }
            )

            alert_ids.append(
                result.scalar()
            )

        print(
            f"Alerts created: "
            f"{len(alert_ids)}"
        )


    # ========================================================
    # SUMMARY
    # ========================================================

    print("\n")
    print("=" * 70)
    print("DATA GENERATION COMPLETED")
    print("=" * 70)

    print(f"""
New records generated:

Areas              : {len(area_ids)}
Citizens           : {len(new_citizen_ids)}
Workers            : {len(new_worker_ids)}
Waste Reports      : {len(report_ids)}
Collection Requests: {len(collection_ids)}
Segregation Ratings: {len(rating_ids)}
Complaints         : {len(complaint_ids)}
Rewards            : {len(reward_ids)}
Penalties          : {len(penalty_ids)}
Vehicles           : {len(vehicle_ids)}
GPS Records        : {NUM_GPS_RECORDS}
Alerts             : {len(alert_ids)}
""")

    print("=" * 70)
    print("Synthetic user password:")
    print(SYNTHETIC_PASSWORD)
    print("=" * 70)

    print(
        "\nIMPORTANT:"
        "\nThis data is synthetic and intended for"
        "\ndevelopment, ETL, analytics and dashboard testing."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()