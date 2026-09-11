from pydantic import BaseModel
from datetime import datetime

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str


class UserUpdate(BaseModel):
    name: str
    email: str
    role: str


class UserResponse(BaseModel):
    user_id: int
    name: str
    email: str
    role: str

    class Config:
        from_attributes = True
class LoginRequest(BaseModel):
    email: str
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