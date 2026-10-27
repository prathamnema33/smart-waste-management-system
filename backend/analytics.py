from sqlalchemy import case, func, text
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends

from auth import require_role, require_roles
from database import get_db
from models import (
    Alert,
    Area,
    CollectionRequest,
    Complaint,
    Penalty,
    RewardTransaction,
    SegregationRating,
    User,
    WasteReport,
)
from schemas import (
    AlertAnalyticsResponse,
    AreaSegregationResponse,
    AnalyticsOverviewResponse,
    CollectionTrendResponse,
    ComplaintAnalyticsResponse,
    ComplaintCategoryCountResponse,
    DailyWasteResponse,
    PenaltyAnalyticsResponse,
    RewardAnalyticsResponse,
    SegregationAnalyticsResponse,
    WasteByAreaResponse,
    WasteByTypeResponse,
    WorkerPerformanceResponse,
)


router = APIRouter(tags=["Monitor Analytics"])


def monitor_only():
    return Depends(require_role("MONITOR"))


@router.get(
    "/monitor/analytics/overview",
    response_model=AnalyticsOverviewResponse,
)
def get_analytics_overview(
    current_user: User = monitor_only(),
    db: Session = Depends(get_db),
):
    waste = db.query(
        func.count(WasteReport.report_id),
        func.coalesce(func.sum(WasteReport.quantity_kg), 0),
    ).one()
    collections = db.query(
        func.count(CollectionRequest.request_id),
        func.count(CollectionRequest.request_id).filter(
            CollectionRequest.status != "COLLECTED"
        ),
        func.count(CollectionRequest.request_id).filter(
            CollectionRequest.status == "COLLECTED"
        ),
    ).one()
    complaints = db.query(
        func.count(Complaint.complaint_id),
        func.count(Complaint.complaint_id).filter(Complaint.status == "OPEN"),
    ).one()
    rewards = db.query(
        func.coalesce(func.sum(RewardTransaction.points), 0),
    ).scalar()
    penalties = db.query(
        func.coalesce(func.sum(Penalty.amount), 0),
    ).scalar()
    open_alerts = db.query(func.count(Alert.alert_id)).filter(
        Alert.status == "OPEN"
    ).scalar()

    total_collections = collections[0]
    collected_collections = collections[2]
    efficiency = (
        (collected_collections / total_collections) * 100
        if total_collections
        else 0
    )

    return {
        "total_waste_reports": waste[0],
        "total_waste_kg": float(waste[1] or 0),
        "total_collections": total_collections,
        "pending_collections": collections[1],
        "collection_efficiency": round(efficiency, 2),
        "total_complaints": complaints[0],
        "open_complaints": complaints[1],
        "total_rewards_points": int(rewards or 0),
        "total_penalty_amount": float(penalties or 0),
        "open_alerts": open_alerts or 0,
    }


@router.get(
    "/monitor/analytics/waste-by-area",
    response_model=list[WasteByAreaResponse],
)
def get_waste_by_area(
    current_user: User = monitor_only(),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            Area.area_id,
            Area.area_name,
            func.count(WasteReport.report_id).label("total_reports"),
            func.coalesce(func.sum(WasteReport.quantity_kg), 0).label("total_waste_kg"),
            func.coalesce(func.avg(WasteReport.quantity_kg), 0).label(
                "average_waste_per_report"
            ),
        )
        .outerjoin(WasteReport, WasteReport.area_id == Area.area_id)
        .group_by(Area.area_id, Area.area_name)
        .order_by(func.coalesce(func.sum(WasteReport.quantity_kg), 0).desc())
        .all()
    )

    return [
        {
            "area_id": row.area_id,
            "area_name": row.area_name,
            "total_reports": row.total_reports,
            "total_waste_kg": float(row.total_waste_kg or 0),
            "average_waste_per_report": float(row.average_waste_per_report or 0),
        }
        for row in rows
    ]


@router.get(
    "/monitor/analytics/waste-by-type",
    response_model=list[WasteByTypeResponse],
)
def get_waste_by_type(
    current_user: User = monitor_only(),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            WasteReport.waste_type,
            func.count(WasteReport.report_id).label("total_reports"),
            func.coalesce(func.sum(WasteReport.quantity_kg), 0).label("total_waste_kg"),
            func.coalesce(func.avg(WasteReport.quantity_kg), 0).label("average_waste_kg"),
        )
        .group_by(WasteReport.waste_type)
        .order_by(func.coalesce(func.sum(WasteReport.quantity_kg), 0).desc())
        .all()
    )

    return [
        {
            "waste_type": row.waste_type,
            "total_reports": row.total_reports,
            "total_waste_kg": float(row.total_waste_kg or 0),
            "average_waste_kg": float(row.average_waste_kg or 0),
        }
        for row in rows
    ]


@router.get(
    "/monitor/analytics/worker-performance",
    response_model=list[WorkerPerformanceResponse],
)
def get_worker_performance(
    current_user: User = monitor_only(),
    db: Session = Depends(get_db),
):
    rows = db.execute(text("""
        SELECT
            worker_id,
            worker_name,
            total_assigned,
            total_collected,
            total_pending,
            collection_efficiency
        FROM worker_performance
        ORDER BY collection_efficiency DESC, worker_id
    """)).mappings().all()
    return [dict(row) for row in rows]


@router.get(
    "/monitor/analytics/complaints",
    response_model=ComplaintAnalyticsResponse,
)
def get_complaint_analytics(
    current_user: User = monitor_only(),
    db: Session = Depends(get_db),
):
    stats = db.query(
        func.count(Complaint.complaint_id),
        func.count(Complaint.complaint_id).filter(Complaint.status == "OPEN"),
        func.count(Complaint.complaint_id).filter(Complaint.status == "IN_PROGRESS"),
        func.count(Complaint.complaint_id).filter(Complaint.status == "RESOLVED"),
    ).one()
    category_rows = (
        db.query(
            Complaint.category,
            func.count(Complaint.complaint_id).label("total"),
        )
        .group_by(Complaint.category)
        .order_by(func.count(Complaint.complaint_id).desc())
        .all()
    )
    return {
        "total_complaints": stats[0],
        "open_complaints": stats[1],
        "in_progress_complaints": stats[2],
        "resolved_complaints": stats[3],
        "by_category": [
            ComplaintCategoryCountResponse(category=category, total=total)
            for category, total in category_rows
        ],
    }


@router.get(
    "/monitor/analytics/segregation",
    response_model=SegregationAnalyticsResponse,
)
def get_segregation_analytics(
    current_user: User = monitor_only(),
    db: Session = Depends(get_db),
):
    stats = db.query(
        func.count(SegregationRating.rating_id),
        func.coalesce(func.avg(SegregationRating.rating), 0),
        func.count(SegregationRating.rating_id).filter(SegregationRating.rating == 5),
        func.count(SegregationRating.rating_id).filter(SegregationRating.rating == 4),
        func.count(SegregationRating.rating_id).filter(SegregationRating.rating == 3),
        func.count(SegregationRating.rating_id).filter(SegregationRating.rating.in_([1, 2])),
    ).one()
    return {
        "total_ratings": stats[0],
        "average_rating": float(stats[1] or 0),
        "excellent_ratings": stats[2],
        "good_ratings": stats[3],
        "average_ratings": stats[4],
        "poor_ratings": stats[5],
    }


@router.get(
    "/monitor/analytics/segregation-by-area",
    response_model=list[AreaSegregationResponse],
)
def get_segregation_by_area(
    current_user: User = Depends(require_roles("MONITOR", "ADMIN")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            Area.area_id,
            Area.area_name,
            Area.latitude,
            Area.longitude,
            func.count(SegregationRating.rating_id).label("total_ratings"),
            func.coalesce(func.avg(SegregationRating.rating), 0).label(
                "average_rating"
            ),
            func.count(SegregationRating.rating_id)
            .filter(SegregationRating.rating == 5)
            .label("excellent_ratings"),
            func.count(SegregationRating.rating_id)
            .filter(SegregationRating.rating == 4)
            .label("good_ratings"),
            func.count(SegregationRating.rating_id)
            .filter(SegregationRating.rating == 3)
            .label("average_ratings"),
            func.count(SegregationRating.rating_id)
            .filter(SegregationRating.rating.in_([1, 2]))
            .label("poor_ratings"),
        )
        .outerjoin(WasteReport, WasteReport.area_id == Area.area_id)
        .outerjoin(
            CollectionRequest,
            CollectionRequest.report_id == WasteReport.report_id,
        )
        .outerjoin(
            SegregationRating,
            SegregationRating.request_id == CollectionRequest.request_id,
        )
        .group_by(
            Area.area_id,
            Area.area_name,
            Area.latitude,
            Area.longitude,
        )
        .order_by(Area.area_id)
        .all()
    )

    results = []
    for row in rows:
        total_ratings = row.total_ratings
        good_ratings = row.excellent_ratings + row.good_ratings
        results.append(
            {
                "area_id": row.area_id,
                "area_name": row.area_name,
                "latitude": float(row.latitude) if row.latitude is not None else None,
                "longitude": (
                    float(row.longitude) if row.longitude is not None else None
                ),
                "total_ratings": total_ratings,
                "average_rating": float(row.average_rating or 0),
                "excellent_ratings": row.excellent_ratings,
                "good_ratings": row.good_ratings,
                "average_ratings": row.average_ratings,
                "poor_ratings": row.poor_ratings,
                "segregation_score": (
                    round(good_ratings / total_ratings * 100, 2)
                    if total_ratings
                    else 0
                ),
            }
        )

    return results


@router.get(
    "/monitor/analytics/rewards",
    response_model=RewardAnalyticsResponse,
)
def get_reward_analytics(
    current_user: User = monitor_only(),
    db: Session = Depends(get_db),
):
    stats = db.query(
        func.count(RewardTransaction.transaction_id),
        func.coalesce(func.sum(RewardTransaction.points), 0),
        func.count(func.distinct(RewardTransaction.citizen_id)),
    ).one()
    return {
        "total_reward_transactions": stats[0],
        "total_points_distributed": int(stats[1] or 0),
        "citizens_receiving_rewards": stats[2],
    }


@router.get(
    "/monitor/analytics/penalties",
    response_model=PenaltyAnalyticsResponse,
)
def get_penalty_analytics(
    current_user: User = monitor_only(),
    db: Session = Depends(get_db),
):
    stats = db.query(
        func.count(Penalty.penalty_id),
        func.coalesce(func.sum(Penalty.amount), 0),
        func.count(func.distinct(Penalty.citizen_id)),
    ).one()
    return {
        "total_penalties": stats[0],
        "total_penalty_amount": float(stats[1] or 0),
        "citizens_penalized": stats[2],
    }


@router.get(
    "/monitor/analytics/alerts",
    response_model=AlertAnalyticsResponse,
)
def get_alert_analytics(
    current_user: User = monitor_only(),
    db: Session = Depends(get_db),
):
    stats = db.query(
        func.count(Alert.alert_id),
        func.count(Alert.alert_id).filter(Alert.status == "OPEN"),
        func.count(Alert.alert_id).filter(Alert.status == "RESOLVED"),
        func.count(Alert.alert_id).filter(Alert.severity == "CRITICAL"),
        func.count(Alert.alert_id).filter(Alert.severity == "HIGH"),
    ).one()
    return {
        "total_alerts": stats[0],
        "open_alerts": stats[1],
        "resolved_alerts": stats[2],
        "critical_alerts": stats[3],
        "high_alerts": stats[4],
    }


@router.get(
    "/monitor/analytics/daily-waste",
    response_model=list[DailyWasteResponse],
)
def get_daily_waste(
    current_user: User = monitor_only(),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(
            func.date(WasteReport.reported_at).label("date"),
            func.count(WasteReport.report_id).label("total_reports"),
            func.coalesce(func.sum(WasteReport.quantity_kg), 0).label("total_waste_kg"),
        )
        .filter(WasteReport.reported_at.isnot(None))
        .group_by(func.date(WasteReport.reported_at))
        .order_by(func.date(WasteReport.reported_at))
        .all()
    )
    return [
        {
            "date": row.date,
            "total_reports": row.total_reports,
            "total_waste_kg": float(row.total_waste_kg or 0),
        }
        for row in rows
    ]


@router.get(
    "/monitor/analytics/collection-trend",
    response_model=list[CollectionTrendResponse],
)
def get_collection_trend(
    current_user: User = monitor_only(),
    db: Session = Depends(get_db),
):
    assigned = (
        db.query(
            func.date(CollectionRequest.assigned_at).label("date"),
            func.count(CollectionRequest.request_id).label("assigned_collections"),
        )
        .filter(CollectionRequest.assigned_at.isnot(None))
        .group_by(func.date(CollectionRequest.assigned_at))
        .subquery()
    )
    completed = (
        db.query(
            func.date(CollectionRequest.collected_at).label("date"),
            func.count(CollectionRequest.request_id).label("completed_collections"),
        )
        .filter(CollectionRequest.collected_at.isnot(None))
        .group_by(func.date(CollectionRequest.collected_at))
        .subquery()
    )
    date_value = func.coalesce(assigned.c.date, completed.c.date).label("date")
    rows = (
        db.query(
            date_value,
            func.coalesce(assigned.c.assigned_collections, 0).label(
                "assigned_collections"
            ),
            func.coalesce(completed.c.completed_collections, 0).label(
                "completed_collections"
            ),
        )
        .select_from(assigned)
        .join(completed, assigned.c.date == completed.c.date, isouter=True)
        .order_by(date_value)
        .all()
    )

    completed_only = (
        db.query(completed)
        .filter(~completed.c.date.in_(db.query(assigned.c.date)))
        .all()
    )
    rows = list(rows) + [
        (row.date, 0, row.completed_collections)
        for row in completed_only
    ]
    rows.sort(key=lambda row: row.date)

    return [
        {
            "date": row[0],
            "assigned_collections": row[1],
            "completed_collections": row[2],
        }
        for row in rows
    ]
