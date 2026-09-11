from sqlalchemy import Column, Integer, String, DateTime, Numeric
from database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String(20), nullable=False)
    created_at = Column(DateTime)


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