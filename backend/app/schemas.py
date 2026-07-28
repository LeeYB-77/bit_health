from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime

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
    birth_date: str  # 레거시 로그인은 생년월일이 필수다. Optional이면 인증 우회 경로가 된다.

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


# --- 비트별장(휴양소) ---

class VillaReservationCreate(BaseModel):
    facility_id: int
    start_date: date          # 체크인
    end_date: date            # 체크아웃 (배타적)
    checkin_time: str         # "15:00"
    checkout_time: str        # "11:00"
    participant_count: int = 1


class VillaReservation(BaseModel):
    id: int
    user_id: int
    facility_id: int
    start_date: date
    end_date: date
    checkin_time: Optional[str] = None
    checkout_time: Optional[str] = None
    requested_checkin_time: Optional[str] = None
    requested_checkout_time: Optional[str] = None
    checkin_time_forced: bool = False
    checkout_time_forced: bool = False
    participant_count: int
    status: str
    booking_type: str
    round_id: Optional[int] = None
    created_at: datetime
    vehicle_count: Optional[int] = None
    vehicle_numbers: Optional[str] = None
    adult_count: Optional[int] = None
    child_count: Optional[int] = None

    class Config:
        from_attributes = True


class VillaExtraInfoUpdate(BaseModel):
    """확정 후 추가 입력사항. 성인+아동 합계가 신청 인원과 달라도 저장은 허용한다."""
    vehicle_count: int = 0
    vehicle_numbers: Optional[str] = None
    adult_count: int = 0
    child_count: int = 0      # 15세 이하


class VillaCancelRequest(BaseModel):
    reason: Optional[str] = None


class VillaBookingRound(BaseModel):
    id: int
    target_year: int
    target_month: int
    apply_start: date
    apply_end: date
    notify_date: date
    status: str

    class Config:
        from_attributes = True


class VillaRoundUpsert(BaseModel):
    """회차 수동 생성·상태 변경. 조기 마감 같은 예외 상황에 쓴다."""
    target_year: int
    target_month: int
    status: Optional[str] = None  # open, closed, notified
