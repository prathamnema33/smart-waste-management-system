from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import get_db
from models import Team, Vehicle, VehicleLocation, Worker, User
from team_zones import refresh_zone_for_area
from schemas import (
    VehicleCreate,
    VehicleResponse,
    VehicleLocationCreate,
    VehicleLocationResponse,
)
from auth import require_role, require_roles


router = APIRouter(tags=["Vehicle GPS"])


def get_vehicle_for_user(
    vehicle_id: int,
    current_user: User,
    db: Session,
):
    vehicle = (
        db.query(Vehicle)
        .filter(Vehicle.vehicle_id == vehicle_id)
        .first()
    )

    if vehicle is None:
        raise HTTPException(
            status_code=404,
            detail="Vehicle not found"
        )

    if current_user.role == "WORKER":
        worker = (
            db.query(Worker)
            .filter(Worker.user_id == current_user.user_id)
            .first()
        )
        if worker is None or vehicle.worker_id != worker.worker_id:
            raise HTTPException(
                status_code=403,
                detail="You do not have access to this vehicle"
            )

    return vehicle


@router.post(
    "/vehicles",
    response_model=VehicleResponse,
    status_code=201
)
def add_vehicle(
    vehicle_data: VehicleCreate,
    current_user: User = Depends(require_role("MONITOR")),
    db: Session = Depends(get_db),
):
    worker = (
        db.query(Worker)
        .filter(Worker.worker_id == vehicle_data.worker_id)
        .first()
    )

    if worker is None:
        raise HTTPException(
            status_code=404,
            detail="Worker not found"
        )

    vehicle = Vehicle(
        vehicle_number=vehicle_data.vehicle_number,
        worker_id=vehicle_data.worker_id,
        status=vehicle_data.status
    )

    try:
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to add vehicle"
        )

    return vehicle


@router.get(
    "/vehicles",
    response_model=list[VehicleResponse]
)
def get_vehicles(
    current_user: User = Depends(require_roles("WORKER", "MONITOR")),
    db: Session = Depends(get_db),
):
    query = db.query(Vehicle)

    if current_user.role == "WORKER":
        worker = (
            db.query(Worker)
            .filter(Worker.user_id == current_user.user_id)
            .first()
        )
        if worker is None:
            raise HTTPException(
                status_code=404,
                detail="Worker profile not found"
            )
        query = query.filter(Vehicle.worker_id == worker.worker_id)

    return query.order_by(Vehicle.vehicle_id).all()


@router.post(
    "/vehicles/{vehicle_id}/locations",
    response_model=VehicleLocationResponse,
    status_code=201
)
def record_vehicle_location(
    vehicle_id: int,
    location_data: VehicleLocationCreate,
    current_user: User = Depends(require_role("WORKER")),
    db: Session = Depends(get_db),
):
    vehicle = get_vehicle_for_user(vehicle_id, current_user, db)
    location = VehicleLocation(
        vehicle_id=vehicle_id,
        latitude=location_data.latitude,
        longitude=location_data.longitude,
        recorded_at=datetime.now()
    )

    try:
        db.add(location)
        db.flush()
        worker = (
            db.query(Worker)
            .filter(Worker.worker_id == vehicle.worker_id)
            .first()
        )
        area_ids = {
            area_id
            for (area_id,) in db.query(Team.area_id)
            .filter(Team.vehicle_id == vehicle_id)
            .all()
        }
        if worker is not None:
            area_ids.add(worker.assigned_area)
        for area_id in sorted(area_ids):
            refresh_zone_for_area(db, area_id)
        db.commit()
        db.refresh(location)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to record vehicle location"
        )

    return location


@router.get(
    "/vehicles/{vehicle_id}/locations/latest",
    response_model=VehicleLocationResponse
)
def get_latest_vehicle_location(
    vehicle_id: int,
    current_user: User = Depends(require_roles("WORKER", "MONITOR")),
    db: Session = Depends(get_db),
):
    get_vehicle_for_user(vehicle_id, current_user, db)
    location = (
        db.query(VehicleLocation)
        .filter(VehicleLocation.vehicle_id == vehicle_id)
        .order_by(
            VehicleLocation.recorded_at.desc(),
            VehicleLocation.location_id.desc()
        )
        .first()
    )

    if location is None:
        raise HTTPException(
            status_code=404,
            detail="No location recorded for this vehicle"
        )

    return location


@router.get(
    "/vehicles/{vehicle_id}/locations",
    response_model=list[VehicleLocationResponse]
)
def get_vehicle_location_history(
    vehicle_id: int,
    current_user: User = Depends(require_roles("WORKER", "MONITOR")),
    db: Session = Depends(get_db),
):
    get_vehicle_for_user(vehicle_id, current_user, db)
    return (
        db.query(VehicleLocation)
        .filter(VehicleLocation.vehicle_id == vehicle_id)
        .order_by(
            VehicleLocation.recorded_at.desc(),
            VehicleLocation.location_id.desc()
        )
        .all()
    )
