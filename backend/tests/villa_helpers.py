# 비트별장 테스트 공용 헬퍼. test_villa.py와 test_villa_admin.py가 함께 쓴다.
from datetime import date, datetime

from app import models
from app.routers import villa as villa_router


def target_month(delta_months=0):
    """현재 접수중인 대상월(오늘 + 2개월)에 delta_months를 더한 (year, month)."""
    today = datetime.now().date()
    return villa_router.shift_month(
        today.year, today.month, villa_router.REGULAR_LEAD_MONTHS + delta_months
    )


def in_target_month(day, delta_months=0):
    y, m = target_month(delta_months)
    return date(y, m, day)


def payload(facility_id, start, end, participant_count=4):
    return {
        "facility_id": facility_id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "checkin_time": "15:00",
        "checkout_time": "11:00",
        "participant_count": participant_count,
    }


def seed(db, user, villa, start, end, status="applied", participant_count=4,
         checkin_time="15:00", checkout_time="11:00"):
    row = models.VillaReservation(
        user_id=user.id,
        facility_id=villa.id,
        start_date=start,
        end_date=end,
        checkin_time=checkin_time,
        checkout_time=checkout_time,
        # 동기화 로직이 강제 해제 시 이 값으로 되돌리므로 항상 함께 채운다.
        requested_checkin_time=checkin_time,
        requested_checkout_time=checkout_time,
        participant_count=participant_count,
        status=status,
        booking_type="regular",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
