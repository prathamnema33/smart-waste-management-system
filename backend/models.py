from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    phone_number = Column(String(16), nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String(20), nullable=False)
    created_at = Column(DateTime)


class Area(Base):
    __tablename__ = "areas"

    area_id = Column(Integer, primary_key=True)
    area_name = Column(String, nullable=False)
    latitude = Column(Numeric(9, 6), nullable=True)
    longitude = Column(Numeric(9, 6), nullable=True)
    locality_name = Column(String(150), nullable=True)
    ward_id = Column(Integer, nullable=True)
    boundary_geojson = Column(Text, nullable=True)
    status = Column(String(30), default="ACTIVE")

class WasteReport(Base):
    __tablename__ = "waste_reports"

    report_id = Column(Integer, primary_key=True)
    citizen_id = Column(Integer, nullable=False)
    area_id = Column(Integer, nullable=False)

    waste_type = Column(String(50), nullable=False)
    quantity_kg = Column(Numeric(10, 2))

    latitude = Column(Numeric(9, 6))
    longitude = Column(Numeric(9, 6))

    priority = Column(String(20), default="NORMAL")
    status = Column(String(30), default="PENDING")

    reported_at = Column(DateTime)
class CollectionRequest(Base):
    __tablename__ = "collection_requests"

    request_id = Column(Integer, primary_key=True)
    report_id = Column(Integer, nullable=False)
    worker_id = Column(Integer, nullable=False)

    assigned_at = Column(DateTime)
    collected_at = Column(DateTime)

    status = Column(String(30), default="ASSIGNED")
class Worker(Base):
    __tablename__ = "workers"

    worker_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    assigned_area = Column(Integer, nullable=False)


class SegregationRating(Base):
    __tablename__ = "segregation_ratings"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_segregation_rating_request"),
    )

    rating_id = Column(Integer, primary_key=True)
    request_id = Column(Integer, nullable=False)
    citizen_id = Column(Integer, nullable=False)
    worker_id = Column(Integer, nullable=False)
    rating = Column(Integer, nullable=False)
    remarks = Column(String, nullable=True)
    rated_at = Column(DateTime, nullable=False)


class RewardTransaction(Base):
    __tablename__ = "reward_transactions"

    transaction_id = Column(Integer, primary_key=True)
    citizen_id = Column(Integer, nullable=False)
    points = Column(Integer, nullable=False)
    transaction_type = Column(String(50), nullable=False)
    reference_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)


class Penalty(Base):
    __tablename__ = "penalties"

    penalty_id = Column(Integer, primary_key=True)
    citizen_id = Column(Integer, nullable=False)
    reason = Column(String(255), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    status = Column(String(30), nullable=False)
    created_at = Column(DateTime, nullable=False)


class Complaint(Base):
    __tablename__ = "complaints"

    complaint_id = Column(Integer, primary_key=True)
    citizen_id = Column(Integer, nullable=False)
    area_id = Column(Integer, nullable=False)
    category = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(String, nullable=True)
    status = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)


class Vehicle(Base):
    __tablename__ = "vehicles"

    vehicle_id = Column(Integer, primary_key=True)
    vehicle_number = Column(String, nullable=False)
    worker_id = Column(Integer, nullable=False)
    status = Column(String, nullable=True)


class VehicleLocation(Base):
    __tablename__ = "vehicle_locations"

    location_id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, nullable=False)
    latitude = Column(Numeric(9, 6), nullable=False)
    longitude = Column(Numeric(9, 6), nullable=False)
    recorded_at = Column(DateTime, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"

    alert_id = Column(Integer, primary_key=True)
    area_id = Column(Integer, nullable=False)
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=True)


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("area_id", name="uq_teams_area"),
    )

    team_id = Column(Integer, primary_key=True)
    team_name = Column(String(100), nullable=False)
    area_id = Column(Integer, ForeignKey("areas.area_id"), nullable=False)
    leader_worker_id = Column(
        Integer, ForeignKey("workers.worker_id"), nullable=False
    )
    vehicle_id = Column(Integer, ForeignKey("vehicles.vehicle_id"), nullable=True)
    min_latitude = Column(Numeric(9, 6), nullable=True)
    max_latitude = Column(Numeric(9, 6), nullable=True)
    min_longitude = Column(Numeric(9, 6), nullable=True)
    max_longitude = Column(Numeric(9, 6), nullable=True)

class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("worker_id", name="uq_team_members_worker"),
    )

    team_id = Column(
        Integer, ForeignKey("teams.team_id", ondelete="CASCADE"), primary_key=True
    )
    worker_id = Column(
        Integer, ForeignKey("workers.worker_id", ondelete="CASCADE"), primary_key=True
    )
class MunicipalWard(Base):
    __tablename__ = "municipal_wards"

    ward_id = Column(Integer, primary_key=True, index=True)
    ward_number = Column(String(20), unique=True, nullable=False)
    ward_name = Column(String(255), nullable=False)
    zone = Column(String(20), nullable=True)
    population = Column(Integer, nullable=True)
    boundary_geojson = Column(Text, nullable=False)
