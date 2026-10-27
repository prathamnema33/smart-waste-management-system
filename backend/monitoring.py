from datetime import datetime
from math import ceil

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from auth import require_role
from database import get_db
from models import (
    Alert,
    Area,
    CollectionRequest,
    Complaint,
    MunicipalWard,
    Team,
    TeamMember,
    User,
    Vehicle,
    VehicleLocation,
    WasteReport,
    Worker,
)
from schemas import MonitoringResponse


router = APIRouter(tags=["Monitoring"])

ACTIVE_STATUSES = ("ASSIGNED", "IN_PROGRESS")


def _valid_coordinates(latitude, longitude) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and -90 <= float(latitude) <= 90
        and -180 <= float(longitude) <= 180
    )


def _upper_quartile(values: list[float]) -> float:
    positive_values = sorted(value for value in values if value > 0)
    if not positive_values:
        return 0
    return positive_values[ceil((len(positive_values) - 1) * 0.75)]


def _lower_quartile(values: list[float]) -> float:
    ordered_values = sorted(values)
    if not ordered_values:
        return 0
    return ordered_values[int((len(ordered_values) - 1) * 0.25)]


@router.get(
    "/monitor/monitoring",
    response_model=MonitoringResponse,
    dependencies=[Depends(require_role("MONITOR"))],
)
def get_monitoring_dashboard(
    db: Session = Depends(get_db),
):
    status_rows = (
        db.query(CollectionRequest.status, func.count(CollectionRequest.request_id))
        .group_by(CollectionRequest.status)
        .all()
    )
    status_counts = {status: count for status, count in status_rows}
    assigned_count = status_counts.get("ASSIGNED", 0)
    in_progress_count = status_counts.get("IN_PROGRESS", 0)
    collected_count = status_counts.get("COLLECTED", 0)
    total_requests = sum(status_counts.values())
    active_count = assigned_count + in_progress_count

    unresolved_status = func.upper(func.coalesce(Alert.status, "OPEN")) != "RESOLVED"
    unresolved_alerts = (
        db.query(func.count(Alert.alert_id))
        .filter(unresolved_status)
        .scalar()
        or 0
    )
    collection_efficiency = (
        round(collected_count / total_requests * 100, 2) if total_requests else 0
    )

    worker_vehicles: dict[int, str] = {}
    for worker_id, vehicle_number in (
        db.query(Vehicle.worker_id, Vehicle.vehicle_number)
        .order_by(Vehicle.vehicle_id)
        .all()
    ):
        worker_vehicles.setdefault(worker_id, vehicle_number)

    worker_teams = {
        worker_id: team_name
        for worker_id, team_name in (
            db.query(TeamMember.worker_id, Team.team_name)
            .join(Team, Team.team_id == TeamMember.team_id)
            .all()
        )
    }

    request_rows = (
        db.query(
            CollectionRequest,
            WasteReport,
            Area,
            MunicipalWard,
            Worker,
            User,
        )
        .join(WasteReport, WasteReport.report_id == CollectionRequest.report_id)
        .outerjoin(Area, Area.area_id == WasteReport.area_id)
        .outerjoin(MunicipalWard, MunicipalWard.ward_id == Area.ward_id)
        .outerjoin(Worker, Worker.worker_id == CollectionRequest.worker_id)
        .outerjoin(User, User.user_id == Worker.user_id)
        .filter(CollectionRequest.status.in_(ACTIVE_STATUSES))
        .order_by(
            func.coalesce(WasteReport.reported_at, CollectionRequest.assigned_at)
            .asc()
            .nullslast(),
            CollectionRequest.request_id,
        )
        .all()
    )

    pending_requests = []
    worker_activity: dict[int, tuple[str, int, str | None, str | None, str | None]] = {}
    for request, report, area, ward, worker, user in request_rows:
        requested_at = report.reported_at or request.assigned_at
        pending_requests.append(
            {
                "request_id": request.request_id,
                "report_id": report.report_id,
                "ward_name": ward.ward_name if ward else None,
                "ward_number": ward.ward_number if ward else None,
                "area_name": area.area_name if area else None,
                "worker_name": user.name if user else None,
                "vehicle_number": (
                    worker_vehicles.get(worker.worker_id) if worker else None
                ),
                "status": request.status,
                "requested_at": requested_at,
            }
        )

        if worker is not None:
            current_activity = worker_activity.get(worker.worker_id)
            activity = (
                request.status,
                request.request_id,
                area.area_name if area else None,
                ward.ward_name if ward else None,
                ward.ward_number if ward else None,
            )
            if current_activity is None or (
                activity[0] == "IN_PROGRESS",
                activity[1],
            ) > (
                current_activity[0] == "IN_PROGRESS",
                current_activity[1],
            ):
                worker_activity[worker.worker_id] = activity

    latest_location_ranked = (
        db.query(
            VehicleLocation.vehicle_id.label("vehicle_id"),
            VehicleLocation.location_id.label("location_id"),
            func.row_number()
            .over(
                partition_by=VehicleLocation.vehicle_id,
                order_by=(
                    VehicleLocation.recorded_at.desc().nullslast(),
                    VehicleLocation.location_id.desc(),
                ),
            )
            .label("position"),
        )
        .subquery()
    )
    LatestLocation = aliased(VehicleLocation)
    latest_location_id = (
        select(latest_location_ranked.c.location_id)
        .where(
            latest_location_ranked.c.vehicle_id == Vehicle.vehicle_id,
            latest_location_ranked.c.position == 1,
        )
        .scalar_subquery()
    )
    vehicle_rows = (
        db.query(Vehicle, Worker, User, Area, MunicipalWard, LatestLocation)
        .join(Worker, Worker.worker_id == Vehicle.worker_id)
        .outerjoin(User, User.user_id == Worker.user_id)
        .outerjoin(Area, Area.area_id == Worker.assigned_area)
        .outerjoin(MunicipalWard, MunicipalWard.ward_id == Area.ward_id)
        .outerjoin(LatestLocation, LatestLocation.location_id == latest_location_id)
        .order_by(Vehicle.vehicle_number)
        .all()
    )

    vehicles = []
    vehicle_map_markers = []
    for vehicle, worker, user, area, ward, location in vehicle_rows:
        activity = worker_activity.get(worker.worker_id)
        area_name = activity[2] if activity and activity[2] else (
            area.area_name if area else None
        )
        ward_name = activity[3] if activity and activity[3] else (
            ward.ward_name if ward else None
        )
        ward_number = activity[4] if activity and activity[4] else (
            ward.ward_number if ward else None
        )
        vehicles.append(
            {
                "vehicle_id": vehicle.vehicle_id,
                "vehicle_number": vehicle.vehicle_number,
                "vehicle_status": vehicle.status,
                "collection_status": activity[0] if activity else None,
                "worker_id": worker.worker_id,
                "worker_name": user.name if user else None,
                "team_name": worker_teams.get(worker.worker_id),
                "area_name": area_name,
                "ward_name": ward_name,
                "ward_number": ward_number,
                "latitude": float(location.latitude) if location else None,
                "longitude": float(location.longitude) if location else None,
                "last_gps_update": location.recorded_at if location else None,
            }
        )
        if location and _valid_coordinates(location.latitude, location.longitude):
            vehicle_map_markers.append(
                {
                    "id": vehicle.vehicle_id,
                    "latitude": float(location.latitude),
                    "longitude": float(location.longitude),
                    "label": vehicle.vehicle_number,
                    "status": activity[0] if activity else vehicle.status,
                    "detail": ", ".join(
                        part for part in (ward_name, area_name, user.name if user else None)
                        if part
                    ),
                    "created_at": location.recorded_at,
                }
            )

    alert_rows = (
        db.query(Alert, Area, MunicipalWard)
        .outerjoin(Area, Area.area_id == Alert.area_id)
        .outerjoin(MunicipalWard, MunicipalWard.ward_id == Area.ward_id)
        .order_by(
            case((unresolved_status, 0), else_=1),
            case(
                (func.upper(func.coalesce(Alert.severity, "")) == "CRITICAL", 0),
                (func.upper(func.coalesce(Alert.severity, "")) == "HIGH", 1),
                (func.upper(func.coalesce(Alert.severity, "")) == "MEDIUM", 2),
                else_=3,
            ),
            Alert.created_at.desc().nullslast(),
            Alert.alert_id.desc(),
        )
        .all()
    )
    alerts = [
        {
            "alert_id": alert.alert_id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "ward_name": ward.ward_name if ward else None,
            "ward_number": ward.ward_number if ward else None,
            "area_name": area.area_name if area else None,
            "message": alert.message,
            "created_at": alert.created_at,
            "status": alert.status,
        }
        for alert, area, ward in alert_rows
    ]
    alert_map_markers = [
        {
            "id": alert.alert_id,
            "latitude": float(area.latitude),
            "longitude": float(area.longitude),
            "label": alert.alert_type,
            "status": alert.severity,
            "detail": alert.message,
            "created_at": alert.created_at,
        }
        for alert, area, _ in alert_rows
        if area
        and _valid_coordinates(area.latitude, area.longitude)
    ]

    report_rows = (
        db.query(WasteReport, Area, MunicipalWard)
        .outerjoin(Area, Area.area_id == WasteReport.area_id)
        .outerjoin(MunicipalWard, MunicipalWard.ward_id == Area.ward_id)
        .filter(
            WasteReport.latitude.isnot(None),
            WasteReport.longitude.isnot(None),
        )
        .order_by(WasteReport.reported_at.desc().nullslast(), WasteReport.report_id.desc())
        .all()
    )
    waste_report_markers = [
        {
            "id": report.report_id,
            "latitude": float(report.latitude),
            "longitude": float(report.longitude),
            "label": f"Report #{report.report_id}",
            "status": report.status,
            "detail": " · ".join(
                part
                for part in (
                    ward.ward_name if ward else None,
                    area.area_name if area else None,
                    report.waste_type,
                )
                if part
            ),
            "created_at": report.reported_at,
        }
        for report, area, ward in report_rows
        if _valid_coordinates(report.latitude, report.longitude)
    ]

    collection_rows = (
        db.query(CollectionRequest, WasteReport, Area, MunicipalWard)
        .join(WasteReport, WasteReport.report_id == CollectionRequest.report_id)
        .outerjoin(Area, Area.area_id == WasteReport.area_id)
        .outerjoin(MunicipalWard, MunicipalWard.ward_id == Area.ward_id)
        .filter(
            WasteReport.latitude.isnot(None),
            WasteReport.longitude.isnot(None),
        )
        .order_by(
            func.coalesce(WasteReport.reported_at, CollectionRequest.assigned_at)
            .desc()
            .nullslast(),
            CollectionRequest.request_id.desc(),
        )
        .all()
    )
    collection_markers = [
        {
            "id": request.request_id,
            "latitude": float(report.latitude),
            "longitude": float(report.longitude),
            "label": f"Collection #{request.request_id}",
            "status": request.status,
            "detail": " · ".join(
                part
                for part in (
                    ward.ward_name if ward else None,
                    area.area_name if area else None,
                    f"Report #{report.report_id}",
                )
                if part
            ),
            "created_at": report.reported_at or request.assigned_at,
        }
        for request, report, area, ward in collection_rows
        if _valid_coordinates(report.latitude, report.longitude)
    ]

    wards = db.query(MunicipalWard).order_by(MunicipalWard.ward_number).all()
    ward_stats = {
        ward.ward_id: {
            "total_waste_kg": 0.0,
            "total_reports": 0,
            "total_requests": 0,
            "pending_collections": 0,
            "collected_collections": 0,
            "total_complaints": 0,
            "open_complaints": 0,
            "unresolved_alerts": 0,
        }
        for ward in wards
    }

    for ward_id, report_count, total_waste in (
        db.query(
            MunicipalWard.ward_id,
            func.count(WasteReport.report_id),
            func.coalesce(func.sum(WasteReport.quantity_kg), 0),
        )
        .join(Area, Area.ward_id == MunicipalWard.ward_id)
        .join(WasteReport, WasteReport.area_id == Area.area_id)
        .group_by(MunicipalWard.ward_id)
        .all()
    ):
        if ward_id in ward_stats:
            ward_stats[ward_id]["total_reports"] = report_count
            ward_stats[ward_id]["total_waste_kg"] = float(total_waste or 0)

    for ward_id, total, pending, collected in (
        db.query(
            MunicipalWard.ward_id,
            func.count(CollectionRequest.request_id),
            func.count(CollectionRequest.request_id).filter(
                CollectionRequest.status.in_(ACTIVE_STATUSES)
            ),
            func.count(CollectionRequest.request_id).filter(
                CollectionRequest.status == "COLLECTED"
            ),
        )
        .join(Area, Area.ward_id == MunicipalWard.ward_id)
        .join(WasteReport, WasteReport.area_id == Area.area_id)
        .outerjoin(
            CollectionRequest,
            CollectionRequest.report_id == WasteReport.report_id,
        )
        .group_by(MunicipalWard.ward_id)
        .all()
    ):
        if ward_id in ward_stats:
            ward_stats[ward_id]["total_requests"] = total
            ward_stats[ward_id]["pending_collections"] = pending
            ward_stats[ward_id]["collected_collections"] = collected

    for ward_id, total_complaints, open_complaints in (
        db.query(
            MunicipalWard.ward_id,
            func.count(Complaint.complaint_id),
            func.count(Complaint.complaint_id).filter(
                func.upper(func.coalesce(Complaint.status, "OPEN")) != "RESOLVED"
            ),
        )
        .join(Area, Area.ward_id == MunicipalWard.ward_id)
        .join(Complaint, Complaint.area_id == Area.area_id)
        .group_by(MunicipalWard.ward_id)
        .all()
    ):
        if ward_id in ward_stats:
            ward_stats[ward_id]["total_complaints"] = total_complaints
            ward_stats[ward_id]["open_complaints"] = open_complaints

    for ward_id, alert_count in (
        db.query(MunicipalWard.ward_id, func.count(Alert.alert_id))
        .join(Area, Area.ward_id == MunicipalWard.ward_id)
        .join(Alert, Alert.area_id == Area.area_id)
        .filter(unresolved_status)
        .group_by(MunicipalWard.ward_id)
        .all()
    ):
        if ward_id in ward_stats:
            ward_stats[ward_id]["unresolved_alerts"] = alert_count

    pending_threshold = _upper_quartile(
        [float(stats["pending_collections"]) for stats in ward_stats.values()]
    )
    waste_threshold = _upper_quartile(
        [float(stats["total_waste_kg"]) for stats in ward_stats.values()]
    )
    complaint_threshold = _upper_quartile(
        [float(stats["open_complaints"]) for stats in ward_stats.values()]
    )
    alert_threshold = _upper_quartile(
        [float(stats["unresolved_alerts"]) for stats in ward_stats.values()]
    )
    ward_efficiencies = [
        stats["collected_collections"] / stats["total_requests"] * 100
        for stats in ward_stats.values()
        if stats["total_requests"]
    ]
    performance_threshold = _lower_quartile(ward_efficiencies)

    ward_results = []
    for ward in wards:
        stats = ward_stats[ward.ward_id]
        efficiency = (
            round(
                stats["collected_collections"] / stats["total_requests"] * 100,
                2,
            )
            if stats["total_requests"]
            else 0
        )
        reasons = []
        if stats["pending_collections"] and stats["pending_collections"] >= pending_threshold:
            reasons.append("High pending collections")
        if stats["total_waste_kg"] and stats["total_waste_kg"] >= waste_threshold:
            reasons.append("High waste generation")
        if (
            stats["total_requests"]
            and efficiency <= performance_threshold
            and efficiency < collection_efficiency
        ):
            reasons.append("Poor collection performance")
        if stats["open_complaints"] and stats["open_complaints"] >= complaint_threshold:
            reasons.append("High open complaint count")
        if stats["unresolved_alerts"] and stats["unresolved_alerts"] >= alert_threshold:
            reasons.append("High unresolved alert count")
        ward_results.append(
            {
                "ward_id": ward.ward_id,
                "ward_name": ward.ward_name,
                "ward_number": ward.ward_number,
                **stats,
                "collection_efficiency": efficiency,
                "attention_level": (
                    "HIGH" if len(reasons) >= 3 else "WATCH" if reasons else "NORMAL"
                ),
                "attention_reasons": reasons,
            }
        )
    ward_results.sort(
        key=lambda ward: (
            -len(ward["attention_reasons"]),
            -ward["pending_collections"],
            -ward["total_waste_kg"],
            ward["ward_number"],
        )
    )

    return {
        "updated_at": datetime.now(),
        "summary": {
            "total_requests": total_requests,
            "assigned": assigned_count,
            "in_progress": in_progress_count,
            "collected": collected_count,
            "active_requests": active_count,
            "unresolved_alerts": unresolved_alerts,
            "collection_efficiency": collection_efficiency,
        },
        "vehicles": vehicles,
        "pending_requests": pending_requests,
        "alerts": alerts,
        "wards": ward_results,
        "map_locations": {
            "vehicles": vehicle_map_markers,
            "waste_reports": waste_report_markers,
            "collections": collection_markers,
            "alerts": alert_map_markers,
        },
    }
