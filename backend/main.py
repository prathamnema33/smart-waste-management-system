from sqlalchemy.orm import Session
from fastapi import FastAPI, Depends, HTTPException
from database import get_db
from models import User, WasteReport, CollectionRequest,Worker
from schemas import UserCreate, UserUpdate, UserResponse, LoginRequest
from jose import jwt
from datetime import datetime
from schemas import (
    UserCreate,
    UserUpdate,
    UserResponse,
    LoginRequest,
    WasteReportCreate,
    WasteReportResponse,
    CollectionRequestCreate,
    CollectionRequestResponse
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
SECRET_KEY = "smart-waste-secret-key"
ALGORITHM = "HS256"
security = HTTPBearer()
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("user_id")

        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    user = (
        db.query(User)
        .filter(User.user_id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found"
        )

    return user
def require_role(required_role: str):

    def role_checker(
        current_user: User = Depends(get_current_user)
    ):
        if current_user.role != required_role:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to access this resource"
            )

        return current_user

    return role_checker
app = FastAPI(
    title="Smart Waste Management API",
    version="1.0.0"
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

@app.get("/users", response_model=list[UserResponse])
def get_users(db: Session = Depends(get_db)):

    users = db.query(User).all()

    return users


# -------------------------
# CREATE USER
# -------------------------

@app.post("/users", response_model=UserResponse)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):

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

@app.get("/users/{user_id}", response_model=UserResponse)
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

@app.put("/users/{user_id}", response_model=UserResponse)
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
@app.delete("/users/{user_id}")
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
    user = (
        db.query(User)
        .filter(User.email == login_data.email)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    if not pwd_context.verify(
        login_data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
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