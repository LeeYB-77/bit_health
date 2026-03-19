from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    sub = Column(String, unique=True, index=True, nullable=True) # SSO UUID
    email = Column(String, nullable=True)
    name = Column(String, index=True)
    birth_date = Column(String, nullable=True)  # YYYYMMDD, nullable for SSO users
    role = Column(String, default="user") # user, admin
    department = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Facility(Base):
    __tablename__ = "facilities"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True) # Gym, ScreenGolf
    type = Column(String) # gym, golf
    capacity = Column(Integer)

class Reservation(Base):
    __tablename__ = "reservations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    facility_id = Column(Integer, ForeignKey("facilities.id"))
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    participant_count = Column(Integer, default=1)
    companions = Column(Text, nullable=True) # JSON string: [{"name": "홍길동", "dept": "인사팀"}, ...]
    status = Column(String, default="reserved") # reserved, canceled, completed

    user = relationship("User")
    facility = relationship("Facility")

class AccessLog(Base):
    __tablename__ = "access_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    facility_id = Column(Integer, ForeignKey("facilities.id"))
    check_in_time = Column(DateTime, default=datetime.utcnow)
    check_out_time = Column(DateTime, nullable=True)

    user = relationship("User")
    facility = relationship("Facility")

class SystemSetting(Base):
    __tablename__ = "system_settings"
    key = Column(String, primary_key=True, index=True)
    value = Column(Text) # JSON string
