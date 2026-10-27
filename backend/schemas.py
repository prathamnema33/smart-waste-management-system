from typing import Literal

from pydantic import BaseModel, Field
from datetime import date, datetime

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: Literal["ADMIN", "MONITOR", "WORKER", "CITIZEN"]


class RegistrationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=150)
    phone_number: str = Field(min_length=7, max_length=32)
    password: str = Field(min_length=8, max_length=72)
    role: Literal["CITIZEN", "WORKER"] = "CITIZEN"


class UserUpdate(BaseModel):
    name: str
    email: str
    role: Literal["ADMIN", "MONITOR", "WORKER", "CITIZEN"]


class UserResponse(BaseModel):
    user_id: int
    name: str
    email: str
    role: str

    class Config:
        from_attributes = True
class LoginRequest(BaseModel):
    email: str | None = None
    user_id: int | None = Field(default=None, ge=1)
    worker_id: int | None = Field(default=None, ge=1)
    identifier: str | None = None
    password: str
class WasteReportCreate(BaseModel):
    area_id: int
    waste_type: str
    quantity_kg: float
    latitude: float
    longitude: float
    priority: str = "NORMAL"


class WasteReportResponse(BaseModel):
    report_id: int
    citizen_id: int
    area_id: int
    waste_type: str
    quantity_kg: float | None
    latitude: float | None
    longitude: float | None
    priority: str
    status: str

    class Config:
        from_attributes = True
class CollectionRequestCreate(BaseModel):
    report_id: int
    worker_id: int


class CollectionRequestResponse(BaseModel):
    request_id: int
    report_id: int
    worker_id: int
    assigned_at: datetime | None
    collected_at: datetime | None
    status: str

    class Config:
        from_attributes = True


class SegregationRatingCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5)


class SegregationRatingResponse(BaseModel):
    rating_id: int
    request_id: int
    worker_id: int
    rating: int
    rated_at: datetime

    class Config:
        from_attributes = True


class RewardTransactionResponse(BaseModel):
    transaction_id: int
    citizen_id: int
    points: int
    transaction_type: str
    reference_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class RewardTotalResponse(BaseModel):
    citizen_id: int
    total_points: int


class PenaltyResponse(BaseModel):
    penalty_id: int
    citizen_id: int
    reason: str
    amount: float
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class RewardStatisticsResponse(BaseModel):
    total_rewards: int
    total_points_distributed: int
    citizens_receiving_rewards: int


class PenaltyStatisticsResponse(BaseModel):
    total_penalties: int
    total_penalty_amount: float
    citizens_penalized: int


class ComplaintCreate(BaseModel):
    area_id: int = Field(..., ge=1)
    category: Literal[
        "MISSED_COLLECTION",
        "ILLEGAL_DUMPING",
        "OVERFLOWING_BIN",
        "WORKER_ISSUE",
        "OTHER"
    ]
    description: str = Field(..., min_length=1)
    priority: Literal["LOW", "NORMAL", "HIGH", "URGENT"] = "NORMAL"


class ComplaintResponse(BaseModel):
    complaint_id: int
    citizen_id: int
    area_id: int
    category: str
    description: str
    priority: str | None
    status: str | None
    created_at: datetime | None
    resolved_at: datetime | None

    class Config:
        from_attributes = True


class ComplaintStatusUpdate(BaseModel):
    status: str


class ComplaintStatisticsResponse(BaseModel):
    total_complaints: int
    open_complaints: int
    in_progress_complaints: int
    resolved_complaints: int


class ComplaintCategoryCountResponse(BaseModel):
    category: str
    total: int


class ComplaintAreaCountResponse(BaseModel):
    area_id: int
    total: int


class VehicleCreate(BaseModel):
    vehicle_number: str = Field(..., min_length=1, max_length=50)
    worker_id: int = Field(..., ge=1)
    status: Literal[
        "AVAILABLE",
        "ASSIGNED",
        "IN_SERVICE",
        "MAINTENANCE",
        "OFFLINE",
        "ACTIVE",
        "INACTIVE",
    ] = "AVAILABLE"


class VehicleResponse(BaseModel):
    vehicle_id: int
    vehicle_number: str
    worker_id: int
    status: str | None

    class Config:
        from_attributes = True


class VehicleLocationCreate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class VehicleLocationResponse(BaseModel):
    location_id: int
    vehicle_id: int
    latitude: float
    longitude: float
    recorded_at: datetime | None

    class Config:
        from_attributes = True


class AlertCreate(BaseModel):
    area_id: int = Field(..., ge=1)
    alert_type: Literal[
        "HIGH_WASTE",
        "PENDING_COLLECTION",
        "REPEATED_COMPLAINTS",
        "VEHICLE_INACTIVE",
        "POOR_SEGREGATION",
        "ILLEGAL_DUMPING"
    ]
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    message: str = Field(..., min_length=1)


class AlertResponse(BaseModel):
    alert_id: int
    area_id: int
    alert_type: str
    severity: str | None
    message: str
    created_at: datetime | None
    status: str | None

    class Config:
        from_attributes = True


class MonitoringStatusCounts(BaseModel):
    total_requests: int
    assigned: int
    in_progress: int
    collected: int
    active_requests: int
    unresolved_alerts: int
    collection_efficiency: float


class MonitoringVehicle(BaseModel):
    vehicle_id: int
    vehicle_number: str
    vehicle_status: str | None
    collection_status: str | None
    worker_id: int
    worker_name: str | None
    team_name: str | None
    area_name: str | None
    ward_name: str | None
    ward_number: str | None
    latitude: float | None
    longitude: float | None
    last_gps_update: datetime | None


class MonitoringPendingRequest(BaseModel):
    request_id: int
    report_id: int
    ward_name: str | None
    ward_number: str | None
    area_name: str | None
    worker_name: str | None
    vehicle_number: str | None
    status: str
    requested_at: datetime | None


class MonitoringAlert(BaseModel):
    alert_id: int
    alert_type: str
    severity: str | None
    ward_name: str | None
    ward_number: str | None
    area_name: str | None
    message: str
    created_at: datetime | None
    status: str | None


class MonitoringWard(BaseModel):
    ward_id: int
    ward_name: str
    ward_number: str
    total_waste_kg: float
    total_reports: int
    total_requests: int
    pending_collections: int
    collected_collections: int
    collection_efficiency: float
    total_complaints: int
    open_complaints: int
    unresolved_alerts: int
    attention_level: str
    attention_reasons: list[str]


class MonitoringMapMarker(BaseModel):
    id: int
    latitude: float
    longitude: float
    label: str
    status: str | None
    detail: str
    created_at: datetime | None


class MonitoringMapLocations(BaseModel):
    vehicles: list[MonitoringMapMarker]
    waste_reports: list[MonitoringMapMarker]
    collections: list[MonitoringMapMarker]
    alerts: list[MonitoringMapMarker]


class MonitoringResponse(BaseModel):
    updated_at: datetime
    summary: MonitoringStatusCounts
    vehicles: list[MonitoringVehicle]
    pending_requests: list[MonitoringPendingRequest]
    alerts: list[MonitoringAlert]
    wards: list[MonitoringWard]
    map_locations: MonitoringMapLocations


class AlertStatisticsResponse(BaseModel):
    total_alerts: int
    open_alerts: int
    resolved_alerts: int
    high_severity_alerts: int


class AnalyticsOverviewResponse(BaseModel):
    total_waste_reports: int
    total_waste_kg: float
    total_collections: int
    pending_collections: int
    collection_efficiency: float
    total_complaints: int
    open_complaints: int
    total_rewards_points: int
    total_penalty_amount: float
    open_alerts: int


class WasteByAreaResponse(BaseModel):
    area_id: int
    area_name: str
    total_reports: int
    total_waste_kg: float
    average_waste_per_report: float


class WasteByTypeResponse(BaseModel):
    waste_type: str
    total_reports: int
    total_waste_kg: float
    average_waste_kg: float


class WorkerPerformanceResponse(BaseModel):
    worker_id: int
    worker_name: str
    total_assigned: int
    total_collected: int
    total_pending: int
    collection_efficiency: float


class ComplaintAnalyticsResponse(BaseModel):
    total_complaints: int
    open_complaints: int
    in_progress_complaints: int
    resolved_complaints: int
    by_category: list[ComplaintCategoryCountResponse]


class SegregationAnalyticsResponse(BaseModel):
    total_ratings: int
    average_rating: float
    excellent_ratings: int
    good_ratings: int
    average_ratings: int
    poor_ratings: int


class AreaSegregationResponse(BaseModel):
    area_id: int
    area_name: str
    latitude: float | None
    longitude: float | None
    total_ratings: int
    average_rating: float
    excellent_ratings: int
    good_ratings: int
    average_ratings: int
    poor_ratings: int
    segregation_score: float


class TeamCreate(BaseModel):
    team_name: str = Field(..., min_length=1, max_length=100)
    area_id: int = Field(..., ge=1)
    leader_worker_id: int = Field(..., ge=1)
    worker_ids: list[int] = Field(..., min_length=1)
    vehicle_id: int | None = Field(default=None, ge=1)


class TeamAreaOption(BaseModel):
    area_id: int
    area_name: str
    has_team: bool


class TeamWorkerOption(BaseModel):
    worker_id: int
    worker_name: str
    area_id: int
    team_id: int | None


class TeamVehicleOption(BaseModel):
    vehicle_id: int
    vehicle_number: str
    worker_id: int
    worker_name: str
    area_id: int
    status: str | None
    team_ids: list[int]


class TeamOptionsResponse(BaseModel):
    areas: list[TeamAreaOption]
    workers: list[TeamWorkerOption]
    vehicles: list[TeamVehicleOption]


class TeamResponse(BaseModel):
    team_id: int
    team_name: str
    area_id: int
    area_name: str
    leader_worker_id: int
    leader_name: str
    worker_ids: list[int]
    worker_names: list[str]
    worker_count: int
    vehicle_id: int | None
    vehicle_number: str | None
    min_latitude: float | None
    max_latitude: float | None
    min_longitude: float | None
    max_longitude: float | None
    zone_boundary: list[list[float]] | None


class RewardAnalyticsResponse(BaseModel):
    total_reward_transactions: int
    total_points_distributed: int
    citizens_receiving_rewards: int


class PenaltyAnalyticsResponse(BaseModel):
    total_penalties: int
    total_penalty_amount: float
    citizens_penalized: int


class AlertAnalyticsResponse(BaseModel):
    total_alerts: int
    open_alerts: int
    resolved_alerts: int
    critical_alerts: int
    high_alerts: int


class DailyWasteResponse(BaseModel):
    date: date
    total_reports: int
    total_waste_kg: float


class CollectionTrendResponse(BaseModel):
    date: date
    assigned_collections: int
    completed_collections: int