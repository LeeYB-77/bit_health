# 비트별장(청평별장/동비재) 예약 신청·조회 API
import calendar
import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, auth, schemas, slack_utils
from ..database import get_db

router = APIRouter(
    prefix="/api/villa",
    tags=["villa"],
    responses={404: {"detail": "Not found"}},
)

# 정규예약은 대상월 2개월 전에 접수한다. (예: 10월 대상 → 8/1~8/31 접수, 8/31 통보)
REGULAR_LEAD_MONTHS = 2

# 기간을 점유하는 상태. cancel_requested는 관리자 승인 전까지 여전히 확정으로 본다.
BLOCKING_STATUSES = ("confirmed", "cancel_requested")

# 달력에 노출하는 상태. canceled/rejected는 제외한다.
VISIBLE_STATUSES = ("applied",) + BLOCKING_STATUSES

# 성수기 규칙은 해마다 바뀔 수 있어 하드코딩하지 않고 SystemSetting으로 둔다.
DEFAULT_VILLA_SETTINGS = {
    "peak_months": [7, 8],
    "peak_max_nights": 2,
    "default_max_nights": None,
    "default_checkin_time": "15:00",
    "default_checkout_time": "11:00",
    "villas": {
        "청평별장": {"address": "", "notice": ""},
        "동비재": {"address": "", "notice": ""},
    },
}


def get_villa_settings_data(db: Session) -> dict:
    setting = db.query(models.SystemSetting).filter(
        models.SystemSetting.key == "villa_settings"
    ).first()
    if setting:
        return json.loads(setting.value)
    return DEFAULT_VILLA_SETTINGS


# --- 날짜 계산 헬퍼 ---

def shift_month(year: int, month: int, delta: int):
    """(year, month)에 delta개월을 더한 (year, month)를 반환한다."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def apply_window_for_target(target_year: int, target_month: int):
    """대상월의 접수 기간과 통보일. 2개월 전 1일~말일 접수, 통보일은 마감일과 같다."""
    y, m = shift_month(target_year, target_month, -REGULAR_LEAD_MONTHS)
    last_day = calendar.monthrange(y, m)[1]
    apply_end = date(y, m, last_day)
    return date(y, m, 1), apply_end, apply_end


def target_month_for_date(d: date):
    """오늘이 d일 때 현재 접수중인 대상월. 접수 기간은 항상 '이번 달 1일~말일'이 된다."""
    return shift_month(d.year, d.month, REGULAR_LEAD_MONTHS)


def nights_of(start_date: date, end_date: date) -> int:
    return (end_date - start_date).days


def months_spanned(start_date: date, end_date: date) -> set:
    """이용 기간이 걸치는 월 번호. 체크아웃 날짜가 속한 월도 포함한다."""
    months = set()
    y, m = start_date.year, start_date.month
    while (y, m) <= (end_date.year, end_date.month):
        months.add(m)
        y, m = shift_month(y, m, 1)
    return months


def max_nights_for(start_date: date, end_date: date, settings: dict):
    """
    이용 기간이 성수기(기본 7·8월) 날짜를 하루라도 포함하면 성수기 상한을 적용한다.
    체크인 월만 보면 6/30~7/3(3박)이 제한을 빠져나가 규칙 취지에 맞지 않는다.
    None이면 제한 없음.
    """
    peak_months = set(settings.get("peak_months") or [])
    if months_spanned(start_date, end_date) & peak_months:
        return settings.get("peak_max_nights")
    return settings.get("default_max_nights")


def overlapping_query(db: Session, facility_id: int, start_date: date, end_date: date, statuses):
    """
    기간이 겹치는 예약. 체크아웃 날짜는 배타적이므로
    8/1~8/3과 8/3~8/5는 겹치지 않는다. (골프 슬롯 겹침과 동일한 패턴)
    """
    return db.query(models.VillaReservation).filter(
        models.VillaReservation.facility_id == facility_id,
        models.VillaReservation.status.in_(statuses),
        models.VillaReservation.start_date < end_date,
        models.VillaReservation.end_date > start_date,
    )


def _get_villa_or_404(db: Session, facility_id: int) -> models.Facility:
    villa = db.query(models.Facility).filter(
        models.Facility.id == facility_id,
        models.Facility.type == "villa",
    ).first()
    if not villa:
        raise HTTPException(status_code=404, detail="별장을 찾을 수 없습니다.")
    return villa


def get_or_create_round(db: Session, target_year: int, target_month: int) -> models.VillaBookingRound:
    row = db.query(models.VillaBookingRound).filter(
        models.VillaBookingRound.target_year == target_year,
        models.VillaBookingRound.target_month == target_month,
    ).first()
    if row:
        return row

    apply_start, apply_end, notify_date = apply_window_for_target(target_year, target_month)
    row = models.VillaBookingRound(
        target_year=target_year,
        target_month=target_month,
        apply_start=apply_start,
        apply_end=apply_end,
        notify_date=notify_date,
        status="open",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --- 조회 ---

@router.get("/facilities")
def list_villas(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    settings = get_villa_settings_data(db)
    per_villa = settings.get("villas") or {}
    villas = db.query(models.Facility).filter(
        models.Facility.type == "villa"
    ).order_by(models.Facility.id).all()

    return [
        {
            "id": v.id,
            "name": v.name,
            "capacity": v.capacity,
            "address": (per_villa.get(v.name) or {}).get("address", ""),
            "notice": (per_villa.get(v.name) or {}).get("notice", ""),
            "default_checkin_time": settings.get("default_checkin_time", "15:00"),
            "default_checkout_time": settings.get("default_checkout_time", "11:00"),
        }
        for v in villas
    ]


@router.get("/current-round")
def get_current_round(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    today = datetime.now().date()
    target_year, target_month = target_month_for_date(today)
    apply_start, apply_end, notify_date = apply_window_for_target(target_year, target_month)

    # 회차 행은 첫 신청 시점에 생성된다. 없으면 기본 open으로 간주한다.
    row = db.query(models.VillaBookingRound).filter(
        models.VillaBookingRound.target_year == target_year,
        models.VillaBookingRound.target_month == target_month,
    ).first()
    status = row.status if row else "open"

    settings = get_villa_settings_data(db)
    return {
        "target_year": target_year,
        "target_month": target_month,
        "apply_start": apply_start,
        "apply_end": apply_end,
        "notify_date": notify_date,
        "status": status,
        "is_open": status == "open",
        "days_left": (apply_end - today).days,
        "peak_months": settings.get("peak_months") or [],
        "peak_max_nights": settings.get("peak_max_nights"),
    }


@router.get("/calendar")
def get_calendar(
    facility_id: int,
    year: int,
    month: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    villa = _get_villa_or_404(db, facility_id)
    if not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="month는 1~12 사이여야 합니다.")

    month_first = date(year, month, 1)
    ny, nm = shift_month(year, month, 1)
    next_month_first = date(ny, nm, 1)

    rows = db.query(models.VillaReservation).filter(
        models.VillaReservation.facility_id == villa.id,
        models.VillaReservation.status.in_(VISIBLE_STATUSES),
        models.VillaReservation.start_date < next_month_first,
        models.VillaReservation.end_date > month_first,
    ).order_by(models.VillaReservation.start_date).all()

    items = []
    for r in rows:
        is_mine = r.user_id == current_user.id
        # 경합 중인 신청은 신청자를 공개하지 않는다. 확정 건과 본인 것만 이름을 준다.
        show_name = is_mine or r.status in BLOCKING_STATUSES
        items.append({
            "id": r.id,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "nights": nights_of(r.start_date, r.end_date),
            "status": r.status,
            "is_mine": is_mine,
            "participant_count": r.participant_count,
            "user_name": (r.user.name if r.user else None) if show_name else None,
            "user_dept": (r.user.department if r.user else None) if show_name else None,
        })

    return {
        "year": year,
        "month": month,
        "facility_id": villa.id,
        "facility_name": villa.name,
        "capacity": villa.capacity,
        "items": items,
    }


@router.get("/my")
def get_my_reservations(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    rows = db.query(models.VillaReservation).filter(
        models.VillaReservation.user_id == current_user.id
    ).order_by(models.VillaReservation.start_date.desc()).all()

    return [
        {
            "id": r.id,
            "facility_id": r.facility_id,
            "facility_name": r.facility.name if r.facility else None,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "nights": nights_of(r.start_date, r.end_date),
            "checkin_time": r.checkin_time,
            "checkout_time": r.checkout_time,
            "participant_count": r.participant_count,
            "status": r.status,
            "booking_type": r.booking_type,
            "cancel_reason": r.cancel_reason,
            # 확정됐지만 아직 차량·이용구성을 입력하지 않은 건
            "needs_extra_info": r.status == "confirmed" and r.extra_info_updated_at is None,
        }
        for r in rows
    ]


# --- 신청 ---

@router.post("/apply", response_model=schemas.VillaReservation)
def apply_villa(
    payload: schemas.VillaReservationCreate,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    villa = _get_villa_or_404(db, payload.facility_id)
    today = datetime.now().date()
    start, end = payload.start_date, payload.end_date

    if start >= end:
        raise HTTPException(
            status_code=400,
            detail="체크아웃 날짜는 체크인 날짜보다 뒤여야 합니다. 최소 1박이 필요합니다.",
        )
    if start < today:
        raise HTTPException(status_code=400, detail="지난 날짜는 신청할 수 없습니다.")
    if payload.participant_count < 1:
        raise HTTPException(status_code=400, detail="사용 인원은 1명 이상이어야 합니다.")
    if villa.capacity and payload.participant_count > villa.capacity:
        raise HTTPException(
            status_code=400,
            detail=f"{villa.name}의 정원은 {villa.capacity}명입니다.",
        )

    settings = get_villa_settings_data(db)
    max_nights = max_nights_for(start, end, settings)
    nights = nights_of(start, end)
    if max_nights is not None and nights > max_nights:
        peak_label = "·".join(f"{m}월" for m in settings.get("peak_months") or [])
        raise HTTPException(
            status_code=400,
            detail=f"{peak_label}이 포함된 기간은 최대 {max_nights}박까지 신청할 수 있습니다. (신청: {nights}박)",
        )

    # 정규예약은 체크인 날짜가 현재 회차의 대상월에 속해야 한다.
    # 월말 걸침 연박(10/31~11/2)은 체크인 기준으로 판정하므로 허용된다.
    target_year, target_month = target_month_for_date(today)
    if (start.year, start.month) != (target_year, target_month):
        raise HTTPException(
            status_code=400,
            detail=f"현재 접수중인 대상월은 {target_year}년 {target_month}월입니다. 체크인 날짜를 확인해 주세요.",
        )

    booking_round = get_or_create_round(db, target_year, target_month)
    if booking_round.status != "open":
        raise HTTPException(status_code=400, detail="해당 회차의 접수가 마감되었습니다.")

    # 확정된 기간과 겹치면 거부. applied끼리는 중복 신청을 허용한다(관리자가 선택).
    if overlapping_query(db, villa.id, start, end, BLOCKING_STATUSES).first():
        raise HTTPException(status_code=409, detail="해당 기간에 이미 확정된 예약이 있습니다.")

    # 본인이 같은 기간에 이미 신청했는지
    mine = overlapping_query(db, villa.id, start, end, ("applied",)).filter(
        models.VillaReservation.user_id == current_user.id
    ).first()
    if mine:
        raise HTTPException(status_code=400, detail="이미 해당 기간에 신청하셨습니다.")

    reservation = models.VillaReservation(
        user_id=current_user.id,
        facility_id=villa.id,
        start_date=start,
        end_date=end,
        checkin_time=payload.checkin_time,
        checkout_time=payload.checkout_time,
        participant_count=payload.participant_count,
        status="applied",
        booking_type="regular",
        round_id=booking_round.id,
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)
    return reservation


# --- 취소 ---

@router.post("/cancel/{reservation_id}")
def cancel_application(
    reservation_id: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """확정 전(applied) 신청만 즉시 취소한다. 다른 신청자에게 영향이 없어 승인이 불필요하다."""
    reservation = db.query(models.VillaReservation).filter(
        models.VillaReservation.id == reservation_id
    ).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다.")
    if reservation.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="권한이 없습니다.")

    if reservation.status != "applied":
        raise HTTPException(
            status_code=400,
            detail="확정된 예약은 취소 요청 후 관리자 승인이 필요합니다.",
        )

    reservation.status = "canceled"
    reservation.canceled_at = datetime.now()
    reservation.canceled_by = current_user.id
    db.commit()
    return {"message": "신청이 취소되었습니다."}


@router.post("/cancel-request/{reservation_id}")
def request_cancel(
    reservation_id: int,
    payload: schemas.VillaCancelRequest,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """확정된 예약의 취소 요청. 관리자 승인 후 실제 취소된다."""
    reservation = db.query(models.VillaReservation).filter(
        models.VillaReservation.id == reservation_id
    ).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
    if reservation.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="권한이 없습니다.")

    if reservation.status != "confirmed":
        raise HTTPException(
            status_code=400,
            detail="확정된 예약만 취소 요청할 수 있습니다.",
        )

    reservation.status = "cancel_requested"
    reservation.cancel_requested_at = datetime.now()
    reservation.cancel_reason = payload.reason
    db.commit()

    # 요청이 방치되면 해당 기간이 계속 묶이므로 관리자에게 즉시 알린다.
    _notify_admins_cancel_request(db, reservation, current_user)

    return {"message": "취소 요청이 접수되었습니다. 관리자 승인 후 취소됩니다."}


def _notify_admins_cancel_request(db: Session, reservation, applicant):
    admins = db.query(models.User).filter(
        models.User.role == "admin",
        models.User.email.isnot(None),
    ).all()

    villa_name = reservation.facility.name if reservation.facility else "비트별장"
    period = f"{reservation.start_date} ~ {reservation.end_date}"

    for admin in admins:
        try:
            slack_utils.notify_villa_cancel_request(
                email=admin.email,
                applicant_name=applicant.name,
                villa_name=villa_name,
                period=period,
                reason=reservation.cancel_reason,
            )
        except Exception as e:
            print(f"Failed to notify admin {admin.id} of villa cancel request: {e}")
