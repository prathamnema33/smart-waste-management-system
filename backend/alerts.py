import os
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from auth import require_role
from database import get_db
from models import (
    Alert,
    CollectionRequest,
    Complaint,
    SegregationRating,
    Vehicle,
    WasteReport,
    Worker,
    User,
)
from schemas import AlertCreate, AlertResponse, AlertStatisticsResponse


router = APIRouter(tags=["Smart Alerts"])

HIGH_WASTE_THRESHOLD_KG = float(os.getenv("ALERT_HIGH_WASTE_THRESHOLD_KG", "100"))
HIGH_WASTE_WINDOW_HOURS = int(os.getenv("ALERT_HIGH_WASTE_WINDOW_HOURS", "24"))
PENDING_COLLECTION_AGE_HOURS = int(os.getenv("ALERT_PENDING_COLLECTION_AGE_HOURS", "24"))
REPEATED_COMPLAINT_THRESHOLD = int(os.getenv("ALERT_REPEATED_COMPLAINT_THRESHOLD", "3"))
REPEATED_COMPLAINT_WINDOW_DAYS = int(os.getenv("ALERT_REPEATED_COMPLAINT_WINDOW_DAYS", "7"))
POOR_SEGREGATION_THRESHOLD = float(os.getenv("ALERT_POOR_SEGREGATION_THRESHOLD", "3"))
POOR_SEGREGATION_MIN_RATINGS = int(os.getenv("ALERT_POOR_SEGREGATION_MIN_RATINGS", "3"))


def create_alert(
    db: Session,
    area_id: int,
    alert_type: str,
    severity: str,
    message: str,
):
    existing_alert = (
        db.query(Alert)
        .filter(
            Alert.area_id == area_id,
            Alert.alert_type == alert_type,
            Alert.status == "OPEN",
        )
        .first()
    )

    if existing_alert is not None:
        return None

    alert = Alert(
        area_id=area_id,
        alert_type=alert_type,
        severity=severity,
        message=message,
        created_at=datetime.now(),
        status="OPEN",
    )
    db.add(alert)
    db.flush()
    return alert


def generate_high_waste_alerts(db: Session) -> int:
    cutoff = datetime.now() - timedelta(hours=HIGH_WASTE_WINDOW_HOURS)
    rows = (
        db.query(
            WasteReport.area_id,
            func.sum(WasteReport.quantity_kg).label("total_quantity"),
        )
        .filter(
            WasteReport.reported_at >= cutoff,
            WasteReport.quantity_kg.isnot(None),
        )
        .group_by(WasteReport.area_id)
        .having(func.sum(WasteReport.quantity_kg) > HIGH_WASTE_THRESHOLD_KG)
        .all()
    )

    created = 0
    for area_id, total_quantity in rows:
        alert = create_alert(
            db=db,
            area_id=area_id,
            alert_type="HIGH_WASTE",
            severity="HIGH",
            message=(
                f"Area {area_id} reported {float(total_quantity):.2f} kg of waste "
                f"in the last {HIGH_WASTE_WINDOW_HOURS} hours."
            ),
        )
        created += int(alert is not None)
    return created


def generate_pending_collection_alerts(db: Session) -> int:
    cutoff = datetime.now() - timedelta(hours=PENDING_COLLECTION_AGE_HOURS)
    area_ids = set()

    pending_reports = (
        db.query(WasteReport.area_id)
        .filter(
            WasteReport.status == "PENDING",
            WasteReport.reported_at < cutoff,
        )
        .distinct()
        .all()
    )
    area_ids.update(area_id for area_id, in pending_reports)

    assigned_requests = (
        db.query(WasteReport.area_id)
        .join(
            CollectionRequest,
            CollectionRequest.report_id == WasteReport.report_id,
        )
        .filter(
            CollectionRequest.status == "ASSIGNED",
            CollectionRequest.assigned_at < cutoff,
        )
        .distinct()
        .all()
    )
    area_ids.update(area_id for area_id, in assigned_requests)

    created = 0
    for area_id in area_ids:
        alert = create_alert(
            db=db,
            area_id=area_id,
            alert_type="PENDING_COLLECTION",
            severity="HIGH",
            message=(
                f"Area {area_id} has waste collections pending for more than "
                f"{PENDING_COLLECTION_AGE_HOURS} hours."
            ),
        )
        created += int(alert is not None)
    return created


def generate_repeated_complaint_alerts(db: Session) -> int:
    cutoff = datetime.now() - timedelta(days=REPEATED_COMPLAINT_WINDOW_DAYS)
    rows = (
        db.query(
            Complaint.area_id,
            func.count(Complaint.complaint_id).label("complaint_count"),
        )
        .filter(Complaint.created_at >= cutoff)
        .group_by(Complaint.area_id)
        .having(func.count(Complaint.complaint_id) >= REPEATED_COMPLAINT_THRESHOLD)
        .all()
    )

    created = 0
    for area_id, complaint_count in rows:
        alert = create_alert(
            db=db,
            area_id=area_id,
            alert_type="REPEATED_COMPLAINTS",
            severity="HIGH",
            message=(
                f"Area {area_id} received {complaint_count} complaints "
                f"in the last {REPEATED_COMPLAINT_WINDOW_DAYS} days."
            ),
        )
        created += int(alert is not None)
    return created


def generate_vehicle_inactive_alerts(db: Session) -> int:
    rows = (
        db.query(Worker.assigned_area, Vehicle.vehicle_number, Vehicle.status)
        .join(Vehicle, Vehicle.worker_id == Worker.worker_id)
        .filter(Vehicle.status.in_(["INACTIVE", "MAINTENANCE"]))
        .all()
    )

    created = 0
    for area_id, vehicle_number, status in rows:
        alert = create_alert(
            db=db,
            area_id=area_id,
            alert_type="VEHICLE_INACTIVE",
            severity="CRITICAL" if status == "MAINTENANCE" else "HIGH",
            message=(
                f"Vehicle {vehicle_number} assigned to area {area_id} "
                f"is currently {status}."
            ),
        )
        created += int(alert is not None)
    return created


def generate_poor_segregation_alerts(db: Session) -> int:
    rows = (
        db.query(
            WasteReport.area_id,
            func.avg(SegregationRating.rating).label("average_rating"),
            func.count(SegregationRating.rating_id).label("rating_count"),
        )
        .join(
            CollectionRequest,
            CollectionRequest.report_id == WasteReport.report_id,
        )
        .join(
            SegregationRating,
            SegregationRating.request_id == CollectionRequest.request_id,
        )
        .group_by(WasteReport.area_id)
        .having(func.avg(SegregationRating.rating) < POOR_SEGREGATION_THRESHOLD)
        .having(func.count(SegregationRating.rating_id) >= POOR_SEGREGATION_MIN_RATINGS)
        .all()
    )

    created = 0
    for area_id, average_rating, rating_count in rows:
        alert = create_alert(
            db=db,
            area_id=area_id,
            alert_type="POOR_SEGREGATION",
            severity="HIGH",
            message=(
                f"Area {area_id} has an average segregation rating of "
                f"{float(average_rating):.2f} across {rating_count} ratings."
            ),
        )
        created += int(alert is not None)
    return created


def generate_all_alerts(db: Session) -> int:
    generators = (
        generate_high_waste_alerts,
        generate_pending_collection_alerts,
        generate_repeated_complaint_alerts,
        generate_vehicle_inactive_alerts,
        generate_poor_segregation_alerts,
    )
    return sum(generator(db) for generator in generators)


@router.get(
    "/monitor/alerts",
    response_model=list[AlertResponse],
)
def get_alerts(
    current_user: User = Depends(require_role("MONITOR")),
    db: Session = Depends(get_db),
):
    return (
        db.query(Alert)
        .order_by(Alert.created_at.desc(), Alert.alert_id.desc())
        .all()
    )


@router.get(
    "/monitor/alerts/open",
    response_model=list[AlertResponse],
)
def get_open_alerts(
    current_user: User = Depends(require_role("MONITOR")),
    db: Session = Depends(get_db),
):
    return (
        db.query(Alert)
        .filter(Alert.status == "OPEN")
        .order_by(Alert.created_at.desc(), Alert.alert_id.desc())
        .all()
    )


@router.get(
    "/monitor/alerts/statistics",
    response_model=AlertStatisticsResponse,
)
def get_alert_statistics(
    current_user: User = Depends(require_role("MONITOR")),
    db: Session = Depends(get_db),
):
    statistics = (
        db.query(
            func.count(Alert.alert_id),
            func.count(Alert.alert_id).filter(Alert.status == "OPEN"),
            func.count(Alert.alert_id).filter(Alert.status == "RESOLVED"),
            func.count(Alert.alert_id).filter(
                Alert.severity.in_(["HIGH", "CRITICAL"])
            ),
        )
        .one()
    )

    return {
        "total_alerts": statistics[0],
        "open_alerts": statistics[1],
        "resolved_alerts": statistics[2],
        "high_severity_alerts": statistics[3],
    }


@router.put(
    "/monitor/alerts/{alert_id}/resolve",
    response_model=AlertResponse,
)
def resolve_alert(
    alert_id: int,
    current_user: User = Depends(require_role("MONITOR")),
    db: Session = Depends(get_db),
):
    alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.status != "OPEN":
        raise HTTPException(status_code=400, detail="Alert is not open")

    alert.status = "RESOLVED"
    try:
        db.commit()
        db.refresh(alert)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to resolve alert",
        )
    return alert


@router.post(
    "/monitor/alerts/generate",
)
def generate_alerts(
    current_user: User = Depends(require_role("MONITOR")),
    db: Session = Depends(get_db),
):
    try:
        created_count = generate_all_alerts(db)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to generate alerts",
        )

    return {
        "new_alerts_created": created_count,
        "message": "Rule-based alerts generated successfully",
    }
