from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class UserBase(BaseModel):
    name: str
    birth_date: Optional[str] = None
    email: Optional[str] = None
    sub: Optional[str] = None
    department: Optional[str] = None
    role: str = "user"

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    name: str
    birth_date: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str
    user_name: str
    role: str
    is_new_user: Optional[bool] = False

class TokenData(BaseModel):
    user_id: Optional[str] = None

class ReservationBase(BaseModel):
    start_time: datetime
    end_time: datetime
    participant_count: int = 1
    companions: Optional[str] = None
    priority: int = 3  # 1: 최우선, 2: 우선, 3: 양보

class ReservationCreate(ReservationBase):
    pass

class Reservation(ReservationBase):
    id: int
    user_id: int
    facility_id: int
    status: str
    priority: int
    
    class Config:
        from_attributes = True
