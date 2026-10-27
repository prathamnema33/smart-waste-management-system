from decimal import Decimal

from sqlalchemy import or_
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from auth import require_roles
from database import get_db
from models import (
    Area,
    Team,
    TeamMember,
    User,
    Vehicle,
    VehicleLocation,
    WasteReport,
    Worker,
)
from schemas import (
    TeamAreaOption,
    TeamCreate,
    TeamOptionsResponse,
    TeamResponse,
    TeamVehicleOption,
    TeamWorkerOption,
)


router = APIRouter(prefix="/monitor/teams", tags=["Monitor Teams"])
team_access = Depends(require_roles("MONITOR", "ADMIN"))


def _valid_coordinate_pair(latitude, longitude) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and -90 <= float(latitude) <= 90
        and -180 <= float(longitude) <= 180
    )


def refresh_zone_for_area(db: Session, area_id: int) -> None:
    team = db.query(Team).filter(Team.area_id == area_id).first()
    if team is None:
        return

    points: list[tuple[float, float]] = []
    area = db.query(Area).filter(Area.area_id == area_id).first()
    if area is not None and _valid_coordinate_pair(area.latitude, area.longitude):
        points.append((float(area.latitude), float(area.longitude)))

    report_points = (
        db.query(WasteReport.latitude, WasteReport.longitude)
        .filter(WasteReport.area_id == area_id)
        .all()
    )
    points.extend(
        (float(latitude), float(longitude))
        for latitude, longitude in report_points
        if _valid_coordinate_pair(latitude, longitude)
    )

    gps_rows = (
        db.query(
            VehicleLocation.vehicle_id,
            VehicleLocation.location_id,
            VehicleLocation.latitude,
            VehicleLocation.longitude,
            VehicleLocation.recorded_at,
        )
        .join(Vehicle, Vehicle.vehicle_id == VehicleLocation.vehicle_id)
        .join(Worker, Worker.worker_id == Vehicle.worker_id)
        .filter(
            or_(
                Worker.assigned_area == area_id,
                Vehicle.vehicle_id.in_(
                    db.query(Team.vehicle_id)
                    .filter(
                        Team.area_id == area_id,
                        Team.vehicle_id.isnot(None),
                    )
                ),
            )
        )
        .order_by(
            VehicleLocation.recorded_at.desc().nullslast(),
            VehicleLocation.location_id.desc(),
        )
        .all()
    )
    seen_vehicles: set[int] = set()
    for row in gps_rows:
        if row.vehicle_id in seen_vehicles:
            continue
        seen_vehicles.add(row.vehicle_id)
        if _valid_coordinate_pair(row.latitude, row.longitude):
            points.append((float(row.latitude), float(row.longitude)))

    if points:
        team.min_latitude = Decimal(str(round(min(lat for lat, _ in points), 6)))
        team.max_latitude = Decimal(str(round(max(lat for lat, _ in points), 6)))
        team.min_longitude = Decimal(str(round(min(lon for _, lon in points), 6)))
        team.max_longitude = Decimal(str(round(max(lon for _, lon in points), 6)))
    else:
        team.min_latitude = None
        team.max_latitude = None
        team.min_longitude = None
        team.max_longitude = None


def _team_response(db: Session, team: Team) -> TeamResponse:
    area = db.query(Area).filter(Area.area_id == team.area_id).one()
    leader = (
        db.query(User.name)
        .join(Worker, Worker.user_id == User.user_id)
        .filter(Worker.worker_id == team.leader_worker_id)
        .scalar()
    )
    members = (
        db.query(Worker.worker_id, User.name)
        .join(User, User.user_id == Worker.user_id)
        .join(TeamMember, TeamMember.worker_id == Worker.worker_id)
        .filter(TeamMember.team_id == team.team_id)
        .order_by(Worker.worker_id)
        .all()
    )
    vehicle = (
        db.query(Vehicle)
        .filter(Vehicle.vehicle_id == team.vehicle_id)
        .first()
        if team.vehicle_id is not None
        else None
    )
    bounds = (
        (
            float(team.min_latitude),
            float(team.max_latitude),
            float(team.min_longitude),
            float(team.max_longitude),
        )
        if None not in (
            team.min_latitude,
            team.max_latitude,
            team.min_longitude,
            team.max_longitude,
        )
        else None
    )

    return TeamResponse(
        team_id=team.team_id,
        team_name=team.team_name,
        area_id=team.area_id,
        area_name=area.area_name,
        leader_worker_id=team.leader_worker_id,
        leader_name=leader or "Unknown",
        worker_ids=[worker_id for worker_id, _ in members],
        worker_names=[name for _, name in members],
        worker_count=len(members),
        vehicle_id=vehicle.vehicle_id if vehicle else None,
        vehicle_number=vehicle.vehicle_number if vehicle else None,
        min_latitude=bounds[0] if bounds else None,
        max_latitude=bounds[1] if bounds else None,
        min_longitude=bounds[2] if bounds else None,
        max_longitude=bounds[3] if bounds else None,
        zone_boundary=(
            [
                [bounds[0], bounds[2]],
                [bounds[0], bounds[3]],
                [bounds[1], bounds[3]],
                [bounds[1], bounds[2]],
            ]
            if bounds
            else None
        ),
    )


@router.get("/options", response_model=TeamOptionsResponse)
def get_team_options(
    current_user: User = team_access,
    db: Session = Depends(get_db),
):
    areas = db.query(Area).order_by(Area.area_name).all()
    existing_area_ids = {
        area_id for (area_id,) in db.query(Team.area_id).all()
    }
    workers = (
        db.query(
            Worker.worker_id,
            User.name,
            Worker.assigned_area,
            TeamMember.team_id,
        )
        .join(User, User.user_id == Worker.user_id)
        .outerjoin(TeamMember, TeamMember.worker_id == Worker.worker_id)
        .order_by(User.name, Worker.worker_id)
        .all()
    )
    vehicles = (
        db.query(
            Vehicle.vehicle_id,
            Vehicle.vehicle_number,
            Vehicle.status,
            Worker.worker_id,
            User.name,
            Worker.assigned_area,
        )
        .join(Worker, Worker.worker_id == Vehicle.worker_id)
        .join(User, User.user_id == Worker.user_id)
        .order_by(Vehicle.vehicle_number, Vehicle.vehicle_id)
        .all()
    )
    vehicle_team_ids: dict[int, list[int]] = {}
    for vehicle_id, team_id in (
        db.query(Team.vehicle_id, Team.team_id)
        .filter(Team.vehicle_id.isnot(None))
        .order_by(Team.team_id)
        .all()
    ):
        vehicle_team_ids.setdefault(vehicle_id, []).append(team_id)
    return TeamOptionsResponse(
        areas=[
            TeamAreaOption(
                area_id=area.area_id,
                area_name=area.area_name,
                has_team=area.area_id in existing_area_ids,
            )
            for area in areas
        ],
        workers=[
            TeamWorkerOption(
                worker_id=worker_id,
                worker_name=name,
                area_id=area_id,
                team_id=team_id,
            )
            for worker_id, name, area_id, team_id in workers
        ],
        vehicles=[
            TeamVehicleOption(
                vehicle_id=vehicle_id,
                vehicle_number=vehicle_number,
                status=status,
                worker_id=worker_id,
                worker_name=name,
                area_id=area_id,
                team_ids=vehicle_team_ids.get(vehicle_id, []),
            )
            for (
                vehicle_id,
                vehicle_number,
                status,
                worker_id,
                name,
                area_id,
            ) in vehicles
        ],
    )


@router.get("", response_model=list[TeamResponse])
def get_teams(
    current_user: User = team_access,
    db: Session = Depends(get_db),
):
    teams = db.query(Team).order_by(Team.team_id).all()
    for team in teams:
        refresh_zone_for_area(db, team.area_id)
    try:
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to refresh team zone boundaries",
        ) from error
    return [_team_response(db, team) for team in teams]


@router.post("", response_model=TeamResponse, status_code=201)
def create_team(
    team_data: TeamCreate,
    current_user: User = team_access,
    db: Session = Depends(get_db),
):
    team_name = team_data.team_name.strip()
    if not team_name:
        raise HTTPException(status_code=422, detail="Team name cannot be blank")

    area = db.query(Area).filter(Area.area_id == team_data.area_id).first()
    if area is None:
        raise HTTPException(status_code=404, detail="Area not found")
    if db.query(Team).filter(Team.area_id == area.area_id).first() is not None:
        raise HTTPException(
            status_code=409,
            detail="A team already exists for this area",
        )

    worker_ids = set(team_data.worker_ids)
    if len(worker_ids) != len(team_data.worker_ids):
        raise HTTPException(status_code=422, detail="Worker selection contains duplicates")
    if team_data.leader_worker_id not in worker_ids:
        raise HTTPException(
            status_code=422,
            detail="The team leader must be one of the selected workers",
        )

    workers = (
        db.query(Worker)
        .filter(Worker.worker_id.in_(worker_ids))
        .all()
    )
    workers_by_id = {worker.worker_id: worker for worker in workers}
    if len(workers_by_id) != len(worker_ids):
        raise HTTPException(status_code=404, detail="One or more workers were not found")
    if any(worker.assigned_area != area.area_id for worker in workers):
        raise HTTPException(
            status_code=422,
            detail="All team workers must already be assigned to the selected area",
        )
    occupied_workers = {
        worker_id
        for (worker_id,) in db.query(TeamMember.worker_id)
        .filter(TeamMember.worker_id.in_(worker_ids))
        .all()
    }
    if occupied_workers:
        raise HTTPException(
            status_code=409,
            detail="One or more workers already belong to a team",
        )

    if team_data.vehicle_id is not None:
        vehicle = (
            db.query(Vehicle)
            .filter(Vehicle.vehicle_id == team_data.vehicle_id)
            .first()
        )
        if vehicle is None:
            raise HTTPException(status_code=404, detail="Vehicle not found")
        if vehicle.status not in {
            None,
            "ACTIVE",
            "AVAILABLE",
            "ASSIGNED",
            "IN_SERVICE",
        }:
            raise HTTPException(
                status_code=409,
                detail="The selected vehicle is unavailable for team assignment",
            )

    team = Team(
        team_name=team_name,
        area_id=area.area_id,
        leader_worker_id=team_data.leader_worker_id,
        vehicle_id=team_data.vehicle_id,
    )
    try:
        db.add(team)
        db.flush()
        db.add_all(
            TeamMember(team_id=team.team_id, worker_id=worker_id)
            for worker_id in sorted(worker_ids)
        )
        refresh_zone_for_area(db, area.area_id)
        db.commit()
        db.refresh(team)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The area, worker, or vehicle was assigned to another team",
        ) from error
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to create team",
        ) from error

    return _team_response(db, team)
