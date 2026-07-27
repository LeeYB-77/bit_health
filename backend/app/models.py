from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, Text, Enum
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
    # 컨테이너 TZ=Asia/Seoul 기준. 다른 곳(AccessLog 등)이 모두 datetime.now()를
    # 명시 전달하는 것과 일관되게 맞춘다. 과거 UTC 기준 값은 백필하지 않는다
    # (어느 행이 UTC이고 어느 행이 KST인지 판별할 근거가 없다).
    created_at = Column(DateTime, default=datetime.now)
    golf_suspended_until = Column(DateTime, nullable=True)  # 미사용 패널티: 이 시각까지 예약 불가

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
    companions = Column(Text, nullable=True)
    status = Column(String, default="reserved") # reserved, canceled, completed, used, no_show
    priority = Column(Integer, default=3)  # 1: 최우선(비트직원), 2: 우선(직원+고객), 3: 양보(직원+가족)
    notified_slack = Column(Boolean, default=False)  # 예약 1시간 전 알림 전송 여부

    user = relationship("User")
    facility = relationship("Facility")

class AccessLog(Base):
    __tablename__ = "access_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    facility_id = Column(Integer, ForeignKey("facilities.id"))
    # gym.py/golf.py의 access 엔드포인트가 항상 datetime.now()를 명시 전달하므로
    # 이 기본값은 실제로는 발화하지 않는다. 선언을 실제 저장값(KST naive)과
    # 정합시키기 위해 정정한다.
    check_in_time = Column(DateTime, default=datetime.now)
    check_out_time = Column(DateTime, nullable=True)

    user = relationship("User")
    facility = relationship("Facility")

class SystemSetting(Base):
    __tablename__ = "system_settings"
    key = Column(String, primary_key=True, index=True)
    value = Column(Text) # JSON string


class VillaBookingRound(Base):
    """
    비트별장 정규예약 회차.
    대상월 2개월 전 1일~말일 접수, 마감일에 확정 결과를 통보한다.
    (예: 2026-10 대상 → 2026-08-01~08-31 접수, 08-31 통보)
    """
    __tablename__ = "villa_booking_rounds"
    id = Column(Integer, primary_key=True, index=True)
    target_year = Column(Integer, index=True)
    target_month = Column(Integer, index=True)
    apply_start = Column(Date)
    apply_end = Column(Date)
    notify_date = Column(Date)
    status = Column(String, default="open")  # open, closed, notified
    # 스케줄러가 주기적으로 돌므로 1회성 알림에는 발송 플래그가 필수다.
    reminder_sent = Column(Boolean, default=False)        # 마감 임박 리마인더
    notify_warning_sent = Column(Boolean, default=False)  # 통보일 미확정 경고
    created_at = Column(DateTime, default=datetime.now)  # KST naive


class VillaReservation(Base):
    """
    비트별장(청평별장/동비재) 예약 신청.
    골프와 생애주기가 달라 Reservation을 재사용하지 않는다.
    신청 → (중복 경합) → 관리자 확정 → 추가입력 순으로 진행된다.
    end_date(체크아웃)는 배타적이므로 8/1~8/3과 8/3~8/5는 겹치지 않는다.
    """
    __tablename__ = "villa_reservations"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    facility_id = Column(Integer, ForeignKey("facilities.id"))

    start_date = Column(Date, index=True)   # 체크인
    end_date = Column(Date, index=True)     # 체크아웃 (배타적)
    checkin_time = Column(String)           # "15:00" 예상 입실
    checkout_time = Column(String)          # "11:00" 예상 퇴실
    participant_count = Column(Integer, default=1)

    # applied, confirmed, cancel_requested, canceled, rejected
    status = Column(String, default="applied", index=True)
    booking_type = Column(String, default="regular")  # regular, open
    round_id = Column(Integer, ForeignKey("villa_booking_rounds.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.now)  # KST naive
    confirmed_at = Column(DateTime, nullable=True)
    confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    notified_confirmed = Column(Boolean, default=False)  # 확정/미선정 통보 발송 여부

    # 확정 후 취소 (관리자 승인 필요)
    cancel_requested_at = Column(DateTime, nullable=True)
    cancel_reason = Column(Text, nullable=True)
    canceled_at = Column(DateTime, nullable=True)
    canceled_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # 확정 후 추가 입력사항
    vehicle_count = Column(Integer, nullable=True)
    vehicle_numbers = Column(Text, nullable=True)  # 쉼표 구분
    adult_count = Column(Integer, nullable=True)
    child_count = Column(Integer, nullable=True)   # 15세 이하
    extra_info_updated_at = Column(DateTime, nullable=True)

    # users를 세 번 참조하므로 foreign_keys를 명시해야 한다.
    user = relationship("User", foreign_keys=[user_id])
    facility = relationship("Facility")
    round = relationship("VillaBookingRound")
