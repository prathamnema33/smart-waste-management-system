from sqlalchemy import Column, Integer, String, DateTime,Text
from database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String(20), nullable=False)
    created_at = Column(DateTime)
class MunicipalWard(Base):
    __tablename__ = "municipal_wards"

    ward_id = Column(Integer, primary_key=True, index=True)
    ward_number = Column(String(20), unique=True, nullable=False)
    ward_name = Column(String(255), nullable=False)
    zone = Column(String(20), nullable=True)
    population = Column(Integer, nullable=True)
    boundary_geojson = Column(Text, nullable=False)