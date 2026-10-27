import re

from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from auth import ALGORITHM, SECRET_KEY, get_current_user, require_role, require_roles
from database import get_db
from team_zones import refresh_zone_for_area
from models import (
    User,
    WasteReport,
    CollectionRequest,
    Worker,
    SegregationRating,
    RewardTransaction,
    Penalty,
    Complaint,
    Vehicle,
    VehicleLocation
)
from schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    LoginRequest,
)
from jose import jwt
from datetime import datetime
from schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    LoginRequest,
    RegistrationRequest,
    WasteReportCreate,
    WasteReportResponse,
    CollectionRequestCreate,
    CollectionRequestResponse,
    SegregationRatingCreate,
    SegregationRatingResponse,
    RewardTransactionResponse,
    RewardTotalResponse,
    PenaltyResponse,
    RewardStatisticsResponse,
    PenaltyStatisticsResponse,
    ComplaintCreate,
    ComplaintResponse,
    ComplaintStatusUpdate,
    ComplaintStatisticsResponse,
    ComplaintCategoryCountResponse,
    ComplaintAreaCountResponse,
    VehicleCreate,
    VehicleResponse,
    VehicleLocationCreate,
    VehicleLocationResponse
)
from passlib.context import CryptContext
app = FastAPI(
    title="Smart Waste Management API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Password hashing configuration
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# -------------------------
# HOME
# -------------------------

@app.get("/")
def home():
    return {
        "message": "API is running"
    }


# -------------------------
# GET ALL USERS
# -------------------------

@app.get(
    "/users",
    response_model=list[UserResponse],
    dependencies=[Depends(require_role("ADMIN"))],
)
def get_users(db: Session = Depends(get_db)):

    users = db.query(User).all()

    return users


# -------------------------
# CREATE USER
# -------------------------

@app.post("/register", response_model=UserResponse, status_code=201)
def register_user(
    registration: RegistrationRequest,
    db: Session = Depends(get_db)
):
    if registration.role == "WORKER":
        raise HTTPException(
            status_code=403,
            detail="Worker accounts must be created and assigned to an area by an administrator"
        )

    name = registration.name.strip()
    email = registration.email.strip().lower()
    if not name:
        raise HTTPException(status_code=422, detail="Full name is required")
    valid_email = re.fullmatch(
        r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
        r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@"
        r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
        r"[A-Za-z]{2,63}",
        email,
    )
    if valid_email is None or len(email) > 150:
        raise HTTPException(status_code=422, detail="Please provide a valid email address")

    phone_input = registration.phone_number.strip()
    if not re.fullmatch(r"\+?[0-9][0-9\s().-]*", phone_input):
        raise HTTPException(status_code=422, detail="Please provide a valid phone number")
    phone_digits = re.sub(r"\D", "", phone_input)
    if not 7 <= len(phone_digits) <= 15:
        raise HTTPException(status_code=422, detail="Phone number must contain 7 to 15 digits")
    phone_number = ("+" if phone_input.startswith("+") else "") + phone_digits
    if len(registration.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=422, detail="Password must be no more than 72 UTF-8 bytes")

    existing_user = db.query(User).filter(func.lower(User.email) == email).first()
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    new_user = User(
        name=name,
        email=email,
        phone_number=phone_number,
        password_hash=pwd_context.hash(registration.password),
        role="CITIZEN",
    )
    db.add(new_user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing_user = db.query(User).filter(func.lower(User.email) == email).first()
        if existing_user is not None:
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists",
            )
        raise
    db.refresh(new_user)
    return new_user


@app.post(
    "/users",
    response_model=UserResponse,
    dependencies=[Depends(require_role("ADMIN"))],
)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    if user.role in {"ADMIN", "MONITOR"}:
        raise HTTPException(
            status_code=403,
            detail="Only an administrator can create an ADMIN or MONITOR account"
        )

    hashed_password = pwd_context.hash(user.password)

    new_user = User(
    name=user.name,
    email=user.email,
    password_hash=hashed_password,
    role=user.role
)

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

@app.get("/users/me", response_model=UserResponse)
def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    return current_user
# -------------------------
# GET USER BY ID
# -------------------------

@app.get(
    "/users/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_role("ADMIN"))],
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db)
):

    user = (
        db.query(User)
        .filter(User.user_id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return user

@app.put(
    "/users/{user_id}",
    response_model=UserResponse,
    dependencies=[Depends(require_role("ADMIN"))],
)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db)
):

    user = (
        db.query(User)
        .filter(User.user_id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    user.name = user_data.name
    user.email = user_data.email
    user.role = user_data.role

    db.commit()
    db.refresh(user)

    return user
@app.delete(
    "/users/{user_id}",
    dependencies=[Depends(require_role("ADMIN"))],
)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    user = (
        db.query(User)
        .filter(User.user_id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    db.delete(user)
    db.commit()

    return {
        "message": "User deleted successfully"
    }
@app.post("/login")
def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    identifier = login_data.identifier or login_data.email
    user_query = db.query(User)
    if login_data.worker_id is not None:
        worker_user_id = (
            db.query(Worker.user_id)
            .filter(Worker.worker_id == login_data.worker_id)
            .scalar()
        )
        user_query = user_query.filter(User.user_id == (worker_user_id or -1))
    elif login_data.user_id is not None:
        user_query = user_query.filter(User.user_id == login_data.user_id)
    elif identifier and identifier.upper().startswith("W:"):
        worker_identifier = identifier[2:]
        worker_user_id = None
        if worker_identifier.isdecimal():
            worker_user_id = (
                db.query(Worker.user_id)
                .filter(Worker.worker_id == int(worker_identifier))
                .scalar()
            )
        user_query = user_query.filter(User.user_id == (worker_user_id or -1))
    elif identifier and identifier.upper().startswith("U:"):
        user_identifier = identifier[2:]
        user_query = user_query.filter(
            User.user_id == (int(user_identifier) if user_identifier.isdecimal() else -1)
        )
    elif identifier and identifier.isdecimal():
        user_query = user_query.filter(User.user_id == int(identifier))
    elif identifier:
        user_query = user_query.filter(func.lower(User.email) == identifier.strip().lower())
    else:
        user_query = user_query.filter(User.user_id == -1)
    user = user_query.first()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid email/user ID or password"
        )

    if not pwd_context.verify(
        login_data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email/user ID or password"
        )

    token_data = {
        "user_id": user.user_id,
        "role": user.role
    }

    access_token = jwt.encode(
        token_data,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@app.get("/citizen/dashboard")
def citizen_dashboard(
    current_user: User = Depends(
        require_role("CITIZEN")
    )
):
    return {
        "message": "Welcome to Citizen Dashboard",
        "user": current_user.name
    }
@app.get("/worker/dashboard")
def worker_dashboard(
    current_user: User = Depends(
        require_role("WORKER")
    )
):
    return {
        "message": "Welcome to Worker Dashboard",
        "user": current_user.name
    }
@app.get("/monitor/dashboard")
def monitor_dashboard(
    current_user: User = Depends(
        require_role("MONITOR")
    )
):
    return {
        "message": "Welcome to Monitor Dashboard",
        "user": current_user.name
    }
@app.post(
    "/waste-reports",
    response_model=WasteReportResponse
)
def create_waste_report(
    report: WasteReportCreate,
    current_user: User = Depends(
        require_role("CITIZEN")
    ),
    db: Session = Depends(get_db)
):
    new_report = WasteReport(
        citizen_id=current_user.user_id,
        area_id=report.area_id,
        waste_type=report.waste_type,
        quantity_kg=report.quantity_kg,
        latitude=report.latitude,
        longitude=report.longitude,
        priority=report.priority,
        status="PENDING"
    )

    db.add(new_report)
    db.flush()
    refresh_zone_for_area(db, new_report.area_id)
    db.commit()
    db.refresh(new_report)

    return new_report
@app.get(
    "/waste-reports/my",
    response_model=list[WasteReportResponse]
)
def get_my_waste_reports(
    current_user: User = Depends(
        require_role("CITIZEN")
    ),
    db: Session = Depends(get_db)
):
    reports = (
        db.query(WasteReport)
        .filter(
            WasteReport.citizen_id == current_user.user_id
        )
        .all()
    )

    return reports
@app.post(
    "/collection-requests",
    response_model=CollectionRequestResponse
)
def create_collection_request(
    request_data: CollectionRequestCreate,
    current_user: User = Depends(
        require_role("MONITOR")
    ),
    db: Session = Depends(get_db)
):
    report = (
        db.query(WasteReport)
        .filter(
            WasteReport.report_id == request_data.report_id
        )
        .first()
    )

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Waste report not found"
        )

    new_request = CollectionRequest(
        report_id=request_data.report_id,
        worker_id=request_data.worker_id,
        status="ASSIGNED"
    )

    db.add(new_request)

    report.status = "ASSIGNED"

    db.commit()
    db.refresh(new_request)

    return new_request
@app.get(
    "/collection-requests/my",
    response_model=list[CollectionRequestResponse]
)
def get_my_collection_requests(
    current_user: User = Depends(
        require_role("WORKER")
    ),
    db: Session = Depends(get_db)
):
    worker = (
        db.query(Worker)
        .filter(
            Worker.user_id == current_user.user_id
        )
        .first()
    )

    if worker is None:
        raise HTTPException(
            status_code=404,
            detail="Worker profile not found"
        )

    requests = (
        db.query(CollectionRequest)
        .filter(
            CollectionRequest.worker_id == worker.worker_id
        )
        .all()
    )

    return requests
@app.put(
    "/collection-requests/{request_id}/collect",
    response_model=CollectionRequestResponse
)
def collect_waste(
    request_id: int,
    current_user: User = Depends(
        require_role("WORKER")
    ),
    db: Session = Depends(get_db)
):
    worker = (
        db.query(Worker)
        .filter(
            Worker.user_id == current_user.user_id
        )
        .first()
    )

    if worker is None:
        raise HTTPException(
            status_code=404,
            detail="Worker profile not found"
        )

    collection = (
        db.query(CollectionRequest)
        .filter(
            CollectionRequest.request_id == request_id,
            CollectionRequest.worker_id == worker.worker_id
        )
        .first()
    )

    if collection is None:
        raise HTTPException(
            status_code=404,
            detail="Collection request not found"
        )

    if collection.status == "COLLECTED":
        raise HTTPException(
            status_code=400,
            detail="Waste already collected"
        )

    collection.status = "COLLECTED"
    collection.collected_at = datetime.now()

    report = (
        db.query(WasteReport)
        .filter(
            WasteReport.report_id == collection.report_id
        )
        .first()
    )

    if report:
        report.status = "COLLECTED"

    db.commit()
    db.refresh(collection)

    return collection


@app.post(
    "/collection-requests/{request_id}/rating",
    response_model=SegregationRatingResponse,
    status_code=201
)
def rate_segregation(
    request_id: int,
    rating_data: SegregationRatingCreate,
    current_user: User = Depends(
        require_role("WORKER")
    ),
    db: Session = Depends(get_db)
):
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

    collection = (
        db.query(CollectionRequest)
        .filter(
            CollectionRequest.request_id == request_id,
            CollectionRequest.worker_id == worker.worker_id
        )
        .first()
    )

    if collection is None:
        raise HTTPException(
            status_code=404,
            detail="Collection request not found"
        )

    if collection.status != "COLLECTED":
        raise HTTPException(
            status_code=400,
            detail="Waste must be collected before it can be rated"
        )

    existing_rating = (
        db.query(SegregationRating)
        .filter(SegregationRating.request_id == request_id)
        .first()
    )

    if existing_rating is not None:
        raise HTTPException(
            status_code=409,
            detail="Collection request has already been rated"
        )

    report = (
        db.query(WasteReport)
        .filter(WasteReport.report_id == collection.report_id)
        .first()
    )

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Waste report not found"
        )

    new_rating = SegregationRating(
        request_id=request_id,
        citizen_id=report.citizen_id,
        worker_id=worker.worker_id,
        rating=rating_data.rating,
        rated_at=datetime.now()
    )

    try:
        db.add(new_rating)
        db.flush()

        points_by_rating = {
            5: 20,
            4: 10
        }
        reward_points = points_by_rating.get(rating_data.rating, 0)

        if reward_points:
            db.add(RewardTransaction(
                citizen_id=report.citizen_id,
                points=reward_points,
                transaction_type="SEGREGATION_REWARD",
                reference_id=new_rating.rating_id,
                created_at=datetime.now()
            ))
        elif rating_data.rating in (1, 2):
            penalty_amount = 100 if rating_data.rating == 1 else 50
            db.add(Penalty(
                citizen_id=report.citizen_id,
                reason=f"Poor segregation rating: {rating_data.rating}",
                amount=penalty_amount,
                status="PENDING",
                created_at=datetime.now()
            ))

        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Collection request has already been rated"
        )
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to save segregation rating"
        )

    db.refresh(new_rating)

    return new_rating


@app.get(
    "/rewards/my",
    response_model=list[RewardTransactionResponse]
)
def get_my_rewards(
    current_user: User = Depends(
        require_role("CITIZEN")
    ),
    db: Session = Depends(get_db)
):
    return (
        db.query(RewardTransaction)
        .filter(RewardTransaction.citizen_id == current_user.user_id)
        .order_by(RewardTransaction.created_at.desc())
        .all()
    )


@app.get(
    "/rewards/my/total",
    response_model=RewardTotalResponse
)
def get_my_total_rewards(
    current_user: User = Depends(
        require_role("CITIZEN")
    ),
    db: Session = Depends(get_db)
):
    total_points = (
        db.query(func.coalesce(func.sum(RewardTransaction.points), 0))
        .filter(RewardTransaction.citizen_id == current_user.user_id)
        .scalar()
    )

    return {
        "citizen_id": current_user.user_id,
        "total_points": int(total_points or 0)
    }


@app.get(
    "/penalties/my",
    response_model=list[PenaltyResponse]
)
def get_my_penalties(
    current_user: User = Depends(
        require_role("CITIZEN")
    ),
    db: Session = Depends(get_db)
):
    return (
        db.query(Penalty)
        .filter(Penalty.citizen_id == current_user.user_id)
        .order_by(Penalty.created_at.desc())
        .all()
    )


@app.get(
    "/monitor/rewards",
    response_model=RewardStatisticsResponse
)
def get_reward_statistics(
    current_user: User = Depends(
        require_role("MONITOR")
    ),
    db: Session = Depends(get_db)
):
    statistics = (
        db.query(
            func.count(RewardTransaction.transaction_id),
            func.coalesce(func.sum(RewardTransaction.points), 0),
            func.count(func.distinct(RewardTransaction.citizen_id))
        )
        .one()
    )

    return {
        "total_rewards": statistics[0],
        "total_points_distributed": int(statistics[1] or 0),
        "citizens_receiving_rewards": statistics[2]
    }


@app.get(
    "/monitor/penalties",
    response_model=PenaltyStatisticsResponse
)
def get_penalty_statistics(
    current_user: User = Depends(
        require_role("MONITOR")
    ),
    db: Session = Depends(get_db)
):
    statistics = (
        db.query(
            func.count(Penalty.penalty_id),
            func.coalesce(func.sum(Penalty.amount), 0),
            func.count(func.distinct(Penalty.citizen_id))
        )
        .one()
    )

    return {
        "total_penalties": statistics[0],
        "total_penalty_amount": float(statistics[1] or 0),
        "citizens_penalized": statistics[2]
    }


@app.post(
    "/complaints",
    response_model=ComplaintResponse,
    status_code=201
)
def create_complaint(
    complaint_data: ComplaintCreate,
    current_user: User = Depends(
        require_role("CITIZEN")
    ),
    db: Session = Depends(get_db)
):
    complaint = Complaint(
        citizen_id=current_user.user_id,
        area_id=complaint_data.area_id,
        category=complaint_data.category,
        description=complaint_data.description,
        priority=complaint_data.priority,
        status="OPEN",
        created_at=datetime.now()
    )

    try:
        db.add(complaint)
        db.commit()
        db.refresh(complaint)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to process complaint"
        )

    return complaint


@app.get(
    "/complaints/my",
    response_model=list[ComplaintResponse]
)
def get_my_complaints(
    current_user: User = Depends(
        require_role("CITIZEN")
    ),
    db: Session = Depends(get_db)
):
    return (
        db.query(Complaint)
        .filter(Complaint.citizen_id == current_user.user_id)
        .order_by(Complaint.created_at.desc())
        .all()
    )


@app.get(
    "/monitor/complaints",
    response_model=list[ComplaintResponse]
)
def get_all_complaints(
    current_user: User = Depends(
        require_role("MONITOR")
    ),
    db: Session = Depends(get_db)
):
    status_order = {
        "OPEN": 1,
        "IN_PROGRESS": 2,
        "RESOLVED": 3
    }

    return (
        db.query(Complaint)
        .order_by(
            case(
                status_order,
                value=Complaint.status,
                else_=4
            ),
            Complaint.created_at.desc()
        )
        .all()
    )


@app.get(
    "/monitor/complaints/statistics",
    response_model=ComplaintStatisticsResponse
)
def get_complaint_statistics(
    current_user: User = Depends(
        require_role("MONITOR")
    ),
    db: Session = Depends(get_db)
):
    statistics = (
        db.query(
            func.count(Complaint.complaint_id),
            func.count(Complaint.complaint_id).filter(
                Complaint.status == "OPEN"
            ),
            func.count(Complaint.complaint_id).filter(
                Complaint.status == "IN_PROGRESS"
            ),
            func.count(Complaint.complaint_id).filter(
                Complaint.status == "RESOLVED"
            )
        )
        .one()
    )

    return {
        "total_complaints": statistics[0],
        "open_complaints": statistics[1],
        "in_progress_complaints": statistics[2],
        "resolved_complaints": statistics[3]
    }


@app.get(
    "/monitor/complaints/by-category",
    response_model=list[ComplaintCategoryCountResponse]
)
def get_complaints_by_category(
    current_user: User = Depends(
        require_role("MONITOR")
    ),
    db: Session = Depends(get_db)
):
    rows = (
        db.query(
            Complaint.category,
            func.count(Complaint.complaint_id).label("total")
        )
        .group_by(Complaint.category)
        .order_by(Complaint.category)
        .all()
    )

    return [
        {
            "category": category,
            "total": total
        }
        for category, total in rows
    ]


@app.get(
    "/monitor/complaints/by-area",
    response_model=list[ComplaintAreaCountResponse]
)
def get_complaints_by_area(
    current_user: User = Depends(
        require_role("MONITOR")
    ),
    db: Session = Depends(get_db)
):
    rows = (
        db.query(
            Complaint.area_id,
            func.count(Complaint.complaint_id).label("total")
        )
        .group_by(Complaint.area_id)
        .order_by(Complaint.area_id)
        .all()
    )

    return [
        {
            "area_id": area_id,
            "total": total
        }
        for area_id, total in rows
    ]


@app.put(
    "/monitor/complaints/{complaint_id}",
    response_model=ComplaintResponse
)
def update_complaint_status(
    complaint_id: int,
    status_data: ComplaintStatusUpdate,
    current_user: User = Depends(
        require_role("MONITOR")
    ),
    db: Session = Depends(get_db)
):
    allowed_statuses = {"OPEN", "IN_PROGRESS", "RESOLVED"}

    if status_data.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail="Invalid complaint status"
        )

    complaint = (
        db.query(Complaint)
        .filter(Complaint.complaint_id == complaint_id)
        .first()
    )

    if complaint is None:
        raise HTTPException(
            status_code=404,
            detail="Complaint not found"
        )

    complaint.status = status_data.status
    if status_data.status == "RESOLVED":
        complaint.resolved_at = datetime.now()
    else:
        complaint.resolved_at = None

    try:
        db.commit()
        db.refresh(complaint)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to process complaint"
        )

    return complaint


from gps import router as gps_router
from alerts import router as alerts_router
from analytics import router as analytics_router
from team_zones import router as teams_router
from monitoring import router as monitoring_router


app.include_router(gps_router)
app.include_router(alerts_router)
app.include_router(analytics_router)
app.include_router(teams_router)
app.include_router(monitoring_router)