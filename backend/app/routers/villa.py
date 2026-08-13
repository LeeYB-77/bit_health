# 비트별장(청평별장/동비재) 예약 신청·조회 API
import calendar
import copy
import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, auth, schemas, slack_utils, villa_notify, villa_content
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
# default_checkin_time/default_checkout_time은 이중 역할이다 — 겹치는 예약이
# 없을 때의 기본 제안 시간이면서, 앞뒤로 붙는 예약이 있을 때 강제되는 "정규 시간"이다.
DEFAULT_VILLA_SETTINGS = {
    "peak_months": [7, 8],
    "peak_max_nights": 2,
    "default_max_nights": None,
    "default_checkin_time": "14:00",
    "default_checkout_time": "12:00",
    "villas": {
        "청평별장": {"address": "경기도 가평군 설악면 유명로 2304-34 르메이에르청평빌라 103동 402호(F층 시드니Ⅱ)", "size": "56평", "notice": ""},
        "동비재": {"address": "강원도 속초시 금호동 630 생모리츠아파트 102동 1201호(속초 청초호 앞에 위치)", "size": "51평", "notice": ""},
    },
}


def get_villa_settings_data(db: Session) -> dict:
    setting = db.query(models.SystemSetting).filter(
        models.SystemSetting.key == "villa_settings"
    ).first()
    if setting:
        return json.loads(setting.value)
    # 호출자가 반환값에 값을 넣어 저장하는 경로가 있어(관리실 메일 설정) 사본을 준다.
    # 원본을 그대로 주면 프로세스가 살아 있는 동안 기본값이 오염된다.
    return copy.deepcopy(DEFAULT_VILLA_SETTINGS)


def save_villa_settings_data(db: Session, settings: dict) -> None:
    setting = db.query(models.SystemSetting).filter(
        models.SystemSetting.key == "villa_settings"
    ).first()
    value = json.dumps(settings, ensure_ascii=False)
    if setting:
        setting.value = value
    else:
        db.add(models.SystemSetting(key="villa_settings", value=value))
    db.commit()


def parking_office_email(db: Session) -> str | None:
    """주차등록 요청 메일을 받을 관리실 주소. 관리자가 설정하기 전에는 None이다."""
    return (get_villa_settings_data(db).get("parking_office_email") or "").strip() or None


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


# --- 입퇴실 시간 동기화 ---
# 같은 날 한쪽이 퇴실하고 다른 쪽이 입실하는 건 허용한다(체크아웃 배타 규칙,
# overlapping_query 참조). 다만 그 경계일에는 정리 시간을 보장하기 위해
# 양쪽 모두 정규 입퇴실 시간을 지켜야 한다. 겹치는 예약이 없는 날짜는
# 신청 시 입력한 시간을 그대로 쓸 수 있다.

def _find_adjacent(db: Session, facility_id: int, boundary_date: date, exclude_id: int, side: str):
    """
    side='checkin' — boundary_date에 퇴실하는 다른 확정 예약(내가 그날 입실한다는 뜻)
    side='checkout' — boundary_date에 입실하는 다른 확정 예약(내가 그날 퇴실한다는 뜻)
    """
    q = db.query(models.VillaReservation).filter(
        models.VillaReservation.facility_id == facility_id,
        models.VillaReservation.status.in_(BLOCKING_STATUSES),
        models.VillaReservation.id != exclude_id,
    )
    if side == "checkin":
        q = q.filter(models.VillaReservation.end_date == boundary_date)
    else:
        q = q.filter(models.VillaReservation.start_date == boundary_date)
    return q.first()


def _apply_boundary_side(reservation, side: str, forced: bool, standard_checkin: str, standard_checkout: str) -> bool:
    """
    한쪽 경계의 강제 여부를 반영한다. 방금 강제로 전환됐을 때만 True를 반환한다
    (알림은 '강제가 새로 걸렸을 때'만 보내면 되고, 해제될 때는 보내지 않는다).
    """
    field = f"{side}_time_forced"
    was_forced = getattr(reservation, field)
    if side == "checkin":
        reservation.checkin_time = standard_checkin if forced else reservation.requested_checkin_time
        reservation.checkin_time_forced = forced
    else:
        reservation.checkout_time = standard_checkout if forced else reservation.requested_checkout_time
        reservation.checkout_time_forced = forced
    return forced and not was_forced


def sync_boundary_times(db: Session, reservation) -> list:
    """
    reservation의 체크인/체크아웃 경계에 인접한 확정 예약이 있는지 확인해 정규 시간
    강제 여부를 갱신한다. 인접한 상대방의 반대편 경계도 함께 갱신된다(둘 다 같은 날을
    나눠 쓰므로 한쪽만 정규 시간을 지키는 건 의미가 없다).

    반환값: 이번 호출로 새로 강제 전환된 (reservation, side) 목록. 통보 대상 판단에 쓴다.
    """
    settings = get_villa_settings_data(db)
    standard_checkin = settings.get("default_checkin_time") or "14:00"
    standard_checkout = settings.get("default_checkout_time") or "12:00"
    newly_forced = []

    neighbor_out = _find_adjacent(db, reservation.facility_id, reservation.start_date, reservation.id, "checkin")
    if _apply_boundary_side(reservation, "checkin", neighbor_out is not None, standard_checkin, standard_checkout):
        newly_forced.append((reservation, "checkin"))
    if neighbor_out is not None:
        if _apply_boundary_side(neighbor_out, "checkout", True, standard_checkin, standard_checkout):
            newly_forced.append((neighbor_out, "checkout"))

    neighbor_in = _find_adjacent(db, reservation.facility_id, reservation.end_date, reservation.id, "checkout")
    if _apply_boundary_side(reservation, "checkout", neighbor_in is not None, standard_checkin, standard_checkout):
        newly_forced.append((reservation, "checkout"))
    if neighbor_in is not None:
        if _apply_boundary_side(neighbor_in, "checkin", True, standard_checkin, standard_checkout):
            newly_forced.append((neighbor_in, "checkin"))

    return newly_forced


def release_boundary_times(db: Session, released_reservation) -> None:
    """
    예약이 취소되어 더 이상 기간을 점유하지 않게 됐을 때, 인접했던 이웃들의 강제
    여부를 재평가한다. 이웃에게 다른 인접 예약이 없다면 신청 시간으로 되돌아간다.
    해제는 통보하지 않는다(요청 범위: 강제가 걸릴 때만 알린다).
    """
    neighbor_out = _find_adjacent(
        db, released_reservation.facility_id, released_reservation.start_date, released_reservation.id, "checkin"
    )
    if neighbor_out is not None:
        sync_boundary_times(db, neighbor_out)

    neighbor_in = _find_adjacent(
        db, released_reservation.facility_id, released_reservation.end_date, released_reservation.id, "checkout"
    )
    if neighbor_in is not None:
        sync_boundary_times(db, neighbor_in)


def _notify_newly_forced(db: Session, reservation, newly_forced: list) -> None:
    """
    newly_forced 중 이 reservation 자신의 항목은 건너뛴다 — 확정/통보 메시지에 이미
    강제 여부가 반영되어 별도 발송이 불필요하다. 인접한 상대방에게만 즉시 알린다.
    """
    for target, side in newly_forced:
        if target.id == reservation.id:
            continue
        try:
            villa_notify.notify_boundary_time_forced(db, target, side)
        except Exception as e:
            print(f"Failed to notify boundary time forced for reservation {target.id}: {e}")


def _get_villa_or_404(db: Session, facility_id: int) -> models.Facility:
    villa = db.query(models.Facility).filter(
        models.Facility.id == facility_id,
        models.Facility.type == "villa",
    ).first()
    if not villa:
        raise HTTPException(status_code=404, detail="별장을 찾을 수 없습니다.")
    return villa


def _booking_mode_for(db: Session, start_date: date, today: date):
    """
    체크인 날짜가 속한 달의 신청 방식을 판정한다.
      regular — 현재 정규예약 접수중인 대상월
      open    — 정규예약 결과 통보가 끝난 달. 남은 날짜를 선착순으로 즉시 확정한다.
      closed  — 아직 접수 대상이 아니거나(미래), 마감됐지만 결과 통보 전인 달
    """
    target_year, target_month = target_month_for_date(today)

    if (start_date.year, start_date.month) == (target_year, target_month):
        booking_round = get_or_create_round(db, target_year, target_month)
        if booking_round.status == "open":
            return "regular", booking_round
        # 조기 마감된 경우. 통보까지 끝났으면 선착순으로 연다.
        if booking_round.status == "notified":
            return "open", booking_round
        return "closed", booking_round

    existing = db.query(models.VillaBookingRound).filter(
        models.VillaBookingRound.target_year == start_date.year,
        models.VillaBookingRound.target_month == start_date.month,
    ).first()
    if existing and existing.status == "notified":
        return "open", existing
    return "closed", existing


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
            "size": (per_villa.get(v.name) or {}).get("size", ""),
            "notice": (per_villa.get(v.name) or {}).get("notice", ""),
            "default_checkin_time": settings.get("default_checkin_time", "14:00"),
            "default_checkout_time": settings.get("default_checkout_time", "12:00"),
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

    # 조회 전용이므로 회차를 새로 만들지 않도록 1일 기준으로 판정만 한다.
    mode, _ = _booking_mode_for(db, month_first, datetime.now().date())

    return {
        "year": year,
        "month": month,
        "facility_id": villa.id,
        "facility_name": villa.name,
        "capacity": villa.capacity,
        "booking_mode": mode,  # regular | open | closed
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
            "checkin_time_forced": r.checkin_time_forced,
            "checkout_time_forced": r.checkout_time_forced,
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

    # 체크인 날짜가 속한 달로 판정한다. 월말 걸침 연박(10/31~11/2)도 체크인 기준이다.
    mode, booking_round = _booking_mode_for(db, start, today)
    if mode == "closed":
        target_year, target_month = target_month_for_date(today)
        raise HTTPException(
            status_code=400,
            detail=(
                f"현재 접수중인 대상월은 {target_year}년 {target_month}월입니다. "
                f"정규예약이 마감된 달은 결과 통보 후 선착순으로 신청할 수 있습니다."
            ),
        )

    is_open_booking = mode == "open"

    # 확정된 기간과 겹치면 거부한다. 선착순 기간은 중복 신청 자체를 막아야 하므로
    # 아직 확정 전인(applied) 다른 신청과도 겹치면 거부한다. 정규예약은 applied끼리
    # 중복 신청을 허용한다(마감 후 관리자가 선정).
    conflict_statuses = VISIBLE_STATUSES if is_open_booking else BLOCKING_STATUSES
    conflict = overlapping_query(db, villa.id, start, end, conflict_statuses).first()
    if conflict:
        if conflict.status in BLOCKING_STATUSES:
            raise HTTPException(status_code=409, detail="해당 기간에 이미 확정된 예약이 있습니다.")
        raise HTTPException(status_code=409, detail="해당 기간은 이미 다른 분이 먼저 신청했습니다. 선착순 신청은 중복 신청이 불가합니다.")

    # 본인이 같은 기간에 이미 신청했는지 (정규예약. 선착순은 위에서 이미 걸러진다)
    if not is_open_booking:
        mine = overlapping_query(db, villa.id, start, end, ("applied",)).filter(
            models.VillaReservation.user_id == current_user.id
        ).first()
        if mine:
            raise HTTPException(status_code=400, detail="이미 해당 기간에 신청하셨습니다.")

    # 선착순도 정규예약과 마찬가지로 관리자가 확정한다(중복 신청은 위에서 이미 막았다).
    reservation = models.VillaReservation(
        user_id=current_user.id,
        facility_id=villa.id,
        start_date=start,
        end_date=end,
        # 초기값은 신청 시간 그대로다. 확정되는 순간 인접 예약이 있으면
        # sync_boundary_times가 정규 시간으로 덮어쓴다.
        checkin_time=payload.checkin_time,
        checkout_time=payload.checkout_time,
        requested_checkin_time=payload.checkin_time,
        requested_checkout_time=payload.checkout_time,
        participant_count=payload.participant_count,
        status="applied",
        booking_type="open" if is_open_booking else "regular",
        round_id=booking_round.id if booking_round else None,
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)

    # 정규예약 대기든 선착순 대기든, 신청이 접수될 때마다 관리자에게 알린다.
    villa_notify.notify_admins_new_application(db, reservation, is_open_booking)

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


# --- 추가 입력사항 (확정 후) ---

def _get_own_reservation_or_error(db: Session, reservation_id: int, current_user):
    reservation = db.query(models.VillaReservation).filter(
        models.VillaReservation.id == reservation_id
    ).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
    # 차량번호 등 개인정보가 담기므로 본인만 접근할 수 있다. 관리자도 이 경로로는 열지 않는다.
    if reservation.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="본인의 예약만 조회할 수 있습니다.")
    return reservation


def _extra_info_payload(reservation):
    total = (reservation.adult_count or 0) + (reservation.child_count or 0)
    return {
        "id": reservation.id,
        "facility_name": reservation.facility.name if reservation.facility else None,
        "start_date": reservation.start_date,
        "end_date": reservation.end_date,
        "nights": nights_of(reservation.start_date, reservation.end_date),
        "checkin_time": reservation.checkin_time,
        "checkout_time": reservation.checkout_time,
        "checkin_time_forced": reservation.checkin_time_forced,
        "checkout_time_forced": reservation.checkout_time_forced,
        "participant_count": reservation.participant_count,
        "status": reservation.status,
        "vehicle_count": reservation.vehicle_count,
        "vehicle_numbers": reservation.vehicle_numbers,
        "adult_count": reservation.adult_count,
        "child_count": reservation.child_count,
        "contact_phone": reservation.contact_phone,
        "submitted": reservation.extra_info_updated_at is not None,
        "composition_total": total,
    }


@router.get("/{reservation_id}/extra")
def get_extra_info(
    reservation_id: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    reservation = _get_own_reservation_or_error(db, reservation_id, current_user)
    return _extra_info_payload(reservation)


@router.post("/{reservation_id}/extra")
def update_extra_info(
    reservation_id: int,
    payload: schemas.VillaExtraInfoUpdate,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    reservation = _get_own_reservation_or_error(db, reservation_id, current_user)
    if reservation.status != "confirmed":
        raise HTTPException(
            status_code=400,
            detail="확정된 예약만 추가 정보를 입력할 수 있습니다.",
        )

    if payload.vehicle_count < 0 or payload.adult_count < 0 or payload.child_count < 0:
        raise HTTPException(status_code=400, detail="인원과 차량 대수는 0 이상이어야 합니다.")

    contact_phone = payload.contact_phone.strip()
    if not contact_phone:
        raise HTTPException(status_code=400, detail="연락처를 입력해 주세요.")

    reservation.vehicle_count = payload.vehicle_count
    reservation.vehicle_numbers = (payload.vehicle_numbers or "").strip() or None
    reservation.adult_count = payload.adult_count
    reservation.child_count = payload.child_count
    reservation.contact_phone = contact_phone
    reservation.extra_info_updated_at = datetime.now()
    db.commit()
    db.refresh(reservation)

    # 확정 후 동행 인원이 바뀌는 건 자연스럽다. 강제로 막지 않고 안내만 한다.
    total = payload.adult_count + payload.child_count
    warning = None
    if total != reservation.participant_count:
        warning = (
            f"입력하신 인원 {total}명이 신청 인원 {reservation.participant_count}명과 다릅니다. "
            f"변경이 필요하면 관리팀에 알려 주세요."
        )

    return {
        "message": "추가 정보를 저장했습니다.",
        "warning": warning,
        # 초안을 함께 돌려주면 이용자가 저장 직후 내용을 확인·수정해 발송할 수 있다.
        "parking_mail": _parking_mail_draft_for(db, reservation),
        **_extra_info_payload(reservation),
    }


def _parking_mail_draft_for(db: Session, reservation) -> dict | None:
    """
    주차등록 요청 메일 초안. 동비재만 대상이고, 차량이 없거나 관리실 주소가
    설정되지 않았으면 보낼 것이 없으므로 None을 준다.
    """
    if not reservation.facility or reservation.facility.name != villa_notify.PARKING_MAIL_VILLA:
        return None
    if not reservation.vehicle_numbers:
        return None
    office_email = parking_office_email(db)
    if not office_email:
        return None
    return {"to": office_email, **villa_notify.parking_mail_draft(reservation)}


@router.post("/{reservation_id}/parking-mail")
def send_parking_mail(
    reservation_id: int,
    payload: schemas.VillaParkingMailSend,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    이용자가 확인·수정한 주차등록 요청 메일을 관리실로 보낸다.
    받는 주소는 관리자 설정값만 쓴다 — 클라이언트가 수신자를 정하게 하면 메일 릴레이가 된다.
    """
    reservation = _get_own_reservation_or_error(db, reservation_id, current_user)
    if reservation.status != "confirmed":
        raise HTTPException(status_code=400, detail="확정된 예약만 주차등록을 요청할 수 있습니다.")
    if not reservation.facility or reservation.facility.name != villa_notify.PARKING_MAIL_VILLA:
        raise HTTPException(
            status_code=400,
            detail=f"{villa_notify.PARKING_MAIL_VILLA} 예약만 주차등록 요청 대상입니다.",
        )

    office_email = parking_office_email(db)
    if not office_email:
        raise HTTPException(
            status_code=400,
            detail="관리실 메일 주소가 설정되지 않았습니다. 관리자에게 문의해 주세요.",
        )

    subject = payload.subject.strip()
    body = payload.body.strip()
    if not subject or not body:
        raise HTTPException(status_code=400, detail="메일 제목과 내용을 입력해 주세요.")

    try:
        villa_notify.send_parking_mail(db, office_email, subject, body)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"메일 발송에 실패했습니다. ({e})")

    return {"message": f"관리실({office_email})로 주차등록 요청 메일을 보냈습니다."}


# --- 이용안내 / 퇴실 체크사항 ---

@router.get("/{reservation_id}/guide")
def get_villa_guide(
    reservation_id: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    reservation = _get_own_reservation_or_error(db, reservation_id, current_user)
    villa_name = reservation.facility.name if reservation.facility else None
    content = villa_content.get_villa_content(villa_name)
    if not content:
        raise HTTPException(status_code=404, detail="이용안내 정보를 찾을 수 없습니다.")

    return {
        "reservation": {
            "id": reservation.id,
            "facility_name": villa_name,
            "start_date": reservation.start_date,
            "end_date": reservation.end_date,
            "checkin_time": reservation.checkin_time,
            "checkout_time": reservation.checkout_time,
            "participant_count": reservation.participant_count,
        },
        "address": content["address"],
        "address_note": content["address_note"],
        "access": content["access"],
        "notes": content["notes"],
        "wifi": content["wifi"],
        "key_return_notice": villa_content.KEY_RETURN_NOTICE,
        "emergency_contact": villa_content.EMERGENCY_CONTACT,
    }


@router.get("/{reservation_id}/checkout")
def get_villa_checkout(
    reservation_id: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    reservation = _get_own_reservation_or_error(db, reservation_id, current_user)
    villa_name = reservation.facility.name if reservation.facility else None
    content = villa_content.get_villa_content(villa_name)
    if not content:
        raise HTTPException(status_code=404, detail="퇴실 체크사항 정보를 찾을 수 없습니다.")

    checked = json.loads(reservation.checkout_checklist_checked) if reservation.checkout_checklist_checked else None

    return {
        "reservation": {
            "id": reservation.id,
            "facility_name": villa_name,
            "start_date": reservation.start_date,
            "end_date": reservation.end_date,
        },
        "checklist": content["checklist"],
        "key_return_notice": villa_content.KEY_RETURN_NOTICE,
        "emergency_contact": villa_content.EMERGENCY_CONTACT,
        "submitted": reservation.checkout_checklist_submitted_at is not None,
        "checked": checked,
        "notes": reservation.checkout_checklist_notes,
    }


@router.post("/{reservation_id}/checkout")
def submit_villa_checkout(
    reservation_id: int,
    payload: schemas.VillaChecklistSubmit,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    reservation = _get_own_reservation_or_error(db, reservation_id, current_user)
    villa_name = reservation.facility.name if reservation.facility else None
    content = villa_content.get_villa_content(villa_name)
    if not content:
        raise HTTPException(status_code=404, detail="퇴실 체크사항 정보를 찾을 수 없습니다.")

    if len(payload.checked) != len(content["checklist"]):
        raise HTTPException(status_code=400, detail="체크리스트 항목 수가 일치하지 않습니다.")

    reservation.checkout_checklist_checked = json.dumps(payload.checked)
    reservation.checkout_checklist_notes = (payload.notes or "").strip() or None
    reservation.checkout_checklist_submitted_at = datetime.now()
    db.commit()
    db.refresh(reservation)

    try:
        villa_notify.notify_admins_checkout_submitted(
            db, reservation, content["checklist"], payload.checked, reservation.checkout_checklist_notes,
        )
    except Exception as e:
        print(f"Failed to notify admins of checkout checklist submission for reservation {reservation.id}: {e}")

    return {"message": "퇴실 체크사항을 제출했습니다."}


def _notify_admins_cancel_request(db: Session, reservation, applicant):
    # 별장 관리 알림 대상(전체 관리자 + 별장 위임 담당자)과 동일한 기준을 쓴다.
    admins = villa_notify.villa_admin_recipients(db)

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
                admin_url=villa_notify.admin_villa_url(),
            )
        except Exception as e:
            print(f"Failed to notify admin {admin.id} of villa cancel request: {e}")


# --- 관리자 ---
# 골프가 golf.py 한 파일에 admin 섹션을 두는 패턴을 따른다.

USAGE_WINDOW_DAYS = 365  # 공정성 판단용 이용 이력 집계 기간


def _group_overlapping(reservations):
    """
    겹치는 신청끼리 연결 요소로 묶는다. A-B가 겹치고 B-C가 겹치면 A·B·C가 한 그룹이다.
    관리자가 '무엇과 무엇이 얽혀 있는지'를 한눈에 보게 하기 위한 표시용 그룹이며,
    실제 미선정 처리는 확정된 건과 '직접 겹치는' 신청에만 적용한다.
    """
    n = len(reservations)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            a, b = reservations[i], reservations[j]
            if (a.facility_id == b.facility_id
                    and a.start_date < b.end_date and a.end_date > b.start_date):
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[rb] = ra

    buckets = {}
    for i, r in enumerate(reservations):
        buckets.setdefault(find(i), []).append(r)
    return list(buckets.values())


def _usage_counts(db: Session, user_ids):
    """최근 1년간 확정 이용 횟수. 중복 경합에서 공정성 판단의 근거로 쓴다."""
    if not user_ids:
        return {}
    since = datetime.now().date() - timedelta(days=USAGE_WINDOW_DAYS)
    rows = db.query(
        models.VillaReservation.user_id,
        func.count(models.VillaReservation.id),
    ).filter(
        models.VillaReservation.user_id.in_(list(user_ids)),
        models.VillaReservation.status.in_(BLOCKING_STATUSES),
        models.VillaReservation.start_date >= since,
    ).group_by(models.VillaReservation.user_id).all()
    return {user_id: count for user_id, count in rows}


def _serialize_application(r, usage_counts):
    return {
        "id": r.id,
        "facility_id": r.facility_id,
        "facility_name": r.facility.name if r.facility else None,
        "user_id": r.user_id,
        "user_name": r.user.name if r.user else "(알 수 없음)",
        "user_dept": r.user.department if r.user else None,
        "start_date": r.start_date,
        "end_date": r.end_date,
        "nights": nights_of(r.start_date, r.end_date),
        "checkin_time": r.checkin_time,
        "checkout_time": r.checkout_time,
        "checkin_time_forced": r.checkin_time_forced,
        "checkout_time_forced": r.checkout_time_forced,
        "participant_count": r.participant_count,
        "status": r.status,
        "booking_type": r.booking_type,
        "created_at": r.created_at,
        "usage_count": usage_counts.get(r.user_id, 0),
        # 확정 후 추가 입력사항 — 관리자가 예약 상세를 볼 때 함께 보여준다.
        "vehicle_count": r.vehicle_count,
        "vehicle_numbers": r.vehicle_numbers,
        "adult_count": r.adult_count,
        "child_count": r.child_count,
        "contact_phone": r.contact_phone,
        "cancel_reason": r.cancel_reason,
        # 키 불출/회수
        "key_number": r.key_number,
        "key_issued_at": r.key_issued_at,
        "key_returned_at": r.key_returned_at,
    }


@router.get("/admin/rounds")
def list_rounds(
    current_user: models.User = Depends(auth.get_current_villa_manager),
    db: Session = Depends(get_db),
):
    rows = db.query(models.VillaBookingRound).order_by(
        models.VillaBookingRound.target_year.desc(),
        models.VillaBookingRound.target_month.desc(),
    ).all()

    counts = dict(
        db.query(models.VillaReservation.round_id, func.count(models.VillaReservation.id))
        .filter(models.VillaReservation.status == "applied")
        .group_by(models.VillaReservation.round_id).all()
    )

    return [
        {
            "id": r.id,
            "target_year": r.target_year,
            "target_month": r.target_month,
            "apply_start": r.apply_start,
            "apply_end": r.apply_end,
            "notify_date": r.notify_date,
            "status": r.status,
            "pending_count": counts.get(r.id, 0),
        }
        for r in rows
    ]


@router.post("/admin/rounds")
def upsert_round(
    payload: schemas.VillaRoundUpsert,
    current_user: models.User = Depends(auth.get_current_villa_manager),
    db: Session = Depends(get_db),
):
    """회차를 만들거나 상태를 바꾼다. 조기 마감 같은 예외 상황용."""
    if not 1 <= payload.target_month <= 12:
        raise HTTPException(status_code=400, detail="target_month는 1~12 사이여야 합니다.")
    if payload.status and payload.status not in ("open", "closed", "notified"):
        raise HTTPException(status_code=400, detail="status는 open, closed, notified 중 하나여야 합니다.")

    row = get_or_create_round(db, payload.target_year, payload.target_month)
    if payload.status:
        row.status = payload.status
        db.commit()
        db.refresh(row)

    return {
        "id": row.id,
        "target_year": row.target_year,
        "target_month": row.target_month,
        "apply_start": row.apply_start,
        "apply_end": row.apply_end,
        "notify_date": row.notify_date,
        "status": row.status,
    }


@router.get("/admin/applications")
def list_applications(
    year: int = None,
    month: int = None,
    facility_id: int = None,
    current_user: models.User = Depends(auth.get_current_villa_manager),
    db: Session = Depends(get_db),
):
    """
    전체 신청 현황. 겹치는 신청끼리 묶어 경합 그룹으로 반환한다. 대기 신청은
    관리자가 회차를 오가며 놓치지 않도록 기간 제한 없이 전부 보여준다.
    year/month는 어떤 회차(대상월) 정보를 함께 내려줄지에만 쓰인다 — 생략하면
    현재 접수중인 대상월 회차를 쓴다.
    """
    if year is None or month is None:
        year, month = target_month_for_date(datetime.now().date())
    if not 1 <= month <= 12:
        raise HTTPException(status_code=400, detail="month는 1~12 사이여야 합니다.")

    base = db.query(models.VillaReservation)
    if facility_id:
        base = base.filter(models.VillaReservation.facility_id == facility_id)

    pending = base.filter(models.VillaReservation.status == "applied").order_by(
        models.VillaReservation.created_at
    ).all()
    confirmed = base.filter(
        models.VillaReservation.status.in_(BLOCKING_STATUSES)
    ).order_by(models.VillaReservation.start_date).all()

    usage = _usage_counts(db, {r.user_id for r in pending} | {r.user_id for r in confirmed})

    groups = []
    for bucket in _group_overlapping(pending):
        bucket.sort(key=lambda r: (r.created_at or datetime.min, r.id))
        groups.append({
            "facility_id": bucket[0].facility_id,
            "facility_name": bucket[0].facility.name if bucket[0].facility else None,
            "start_date": min(r.start_date for r in bucket),
            "end_date": max(r.end_date for r in bucket),
            "count": len(bucket),
            "contested": len(bucket) > 1,
            "applications": [_serialize_application(r, usage) for r in bucket],
        })
    groups.sort(key=lambda g: (g["start_date"], g["facility_id"]))

    booking_round = db.query(models.VillaBookingRound).filter(
        models.VillaBookingRound.target_year == year,
        models.VillaBookingRound.target_month == month,
    ).first()
    # 통보 대상 건수는 "이 회차에 속한" 확정 건 기준이어야 한다. confirmed는 더 이상
    # 기간으로 좁혀지지 않으므로(전체 조회) 회차 무관 데이터가 섞이지 않도록 round_id로 직접 센다.
    not_yet_notified = (
        db.query(models.VillaReservation)
        .filter(
            models.VillaReservation.round_id == booking_round.id,
            models.VillaReservation.status == "confirmed",
            models.VillaReservation.notified_confirmed == False,
        ).count()
        if booking_round else 0
    )

    return {
        "year": year,
        "month": month,
        "pending_total": len(pending),
        "contested_groups": sum(1 for g in groups if g["contested"]),
        "groups": groups,
        "confirmed": [_serialize_application(r, usage) for r in confirmed],
        "round": {
            "id": booking_round.id,
            "status": booking_round.status,
            "apply_end": booking_round.apply_end,
            "notify_date": booking_round.notify_date,
        } if booking_round else None,
        "unnotified_count": not_yet_notified,
    }


@router.post("/admin/confirm/{reservation_id}")
def confirm_application(
    reservation_id: int,
    current_user: models.User = Depends(auth.get_current_villa_manager),
    db: Session = Depends(get_db),
):
    reservation = db.query(models.VillaReservation).filter(
        models.VillaReservation.id == reservation_id
    ).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다.")
    if reservation.status != "applied":
        raise HTTPException(status_code=400, detail="신청 상태인 건만 확정할 수 있습니다.")

    if overlapping_query(
        db, reservation.facility_id, reservation.start_date, reservation.end_date, BLOCKING_STATUSES
    ).first():
        raise HTTPException(status_code=409, detail="해당 기간에 이미 확정된 예약이 있습니다.")

    reservation.status = "confirmed"
    reservation.confirmed_at = datetime.now()
    reservation.confirmed_by = current_user.id

    # 직접 겹치는 신청만 미선정 처리한다. 연결 요소 전체를 떨어뜨리면
    # 확정 건과 겹치지 않는 신청까지 부당하게 탈락한다.
    others = overlapping_query(
        db, reservation.facility_id, reservation.start_date, reservation.end_date, ("applied",)
    ).filter(models.VillaReservation.id != reservation.id).all()
    for other in others:
        other.status = "rejected"

    db.commit()

    # 방금 확정으로 이 예약이 기간을 점유하게 됐으니 인접 예약과의 정규 시간을 동기화한다.
    # 이 예약 자신의 강제 여부는 나중에 admin/notify가 보낼 확정 메시지에 반영되므로
    # 여기서는 이웃에게만 즉시 알린다.
    newly_forced = sync_boundary_times(db, reservation)
    db.commit()
    _notify_newly_forced(db, reservation, newly_forced)

    # 정규예약 확정 통보는 마감일 일괄 통보(notify_due_rounds)에서 나간다. 하지만
    # 선착순 회차는 이미 그 통보가 끝난(notified) 상태라 스케줄러가 다시 봐주지
    # 않으므로, 확정하는 이 자리에서 바로 통보해야 한다.
    if reservation.booking_type == "open":
        villa_notify.notify_confirmed(db, reservation)  # 강제 여부가 메시지에 반영된다
        reservation.notified_confirmed = True
        db.commit()

    return {
        "message": "예약을 확정했습니다.",
        "rejected_count": len(others),
    }


@router.get("/admin/cancel-requests")
def list_cancel_requests(
    current_user: models.User = Depends(auth.get_current_villa_manager),
    db: Session = Depends(get_db),
):
    rows = db.query(models.VillaReservation).filter(
        models.VillaReservation.status == "cancel_requested"
    ).order_by(models.VillaReservation.cancel_requested_at).all()

    return [
        {
            "id": r.id,
            "facility_name": r.facility.name if r.facility else None,
            "user_name": r.user.name if r.user else "(알 수 없음)",
            "user_dept": r.user.department if r.user else None,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "nights": nights_of(r.start_date, r.end_date),
            "participant_count": r.participant_count,
            "cancel_requested_at": r.cancel_requested_at,
            "cancel_reason": r.cancel_reason,
        }
        for r in rows
    ]


def _get_cancel_requested_or_400(db: Session, reservation_id: int):
    reservation = db.query(models.VillaReservation).filter(
        models.VillaReservation.id == reservation_id
    ).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
    if reservation.status != "cancel_requested":
        raise HTTPException(status_code=400, detail="취소 요청 상태인 건만 처리할 수 있습니다.")
    return reservation


@router.post("/admin/cancel-approve/{reservation_id}")
def approve_cancel(
    reservation_id: int,
    current_user: models.User = Depends(auth.get_current_villa_manager),
    db: Session = Depends(get_db),
):
    """승인하면 해당 기간이 풀려 다시 신청 가능해진다."""
    reservation = _get_cancel_requested_or_400(db, reservation_id)
    reservation.status = "canceled"
    reservation.canceled_at = datetime.now()
    reservation.canceled_by = current_user.id
    db.commit()

    # 이 예약이 빠지면서 인접 이웃이 정규 시간 강제에서 풀릴 수 있다(다른 인접이 없다면).
    release_boundary_times(db, reservation)
    db.commit()

    villa_notify.notify_cancel_approved(db, reservation)
    return {"message": "취소를 승인했습니다. 해당 기간이 다시 열립니다."}


@router.post("/admin/cancel-reject/{reservation_id}")
def reject_cancel(
    reservation_id: int,
    current_user: models.User = Depends(auth.get_current_villa_manager),
    db: Session = Depends(get_db),
):
    """반려하면 확정 상태로 되돌아간다. 요청 흔적을 남기면 UI에 취소 요청중으로 잘못 보인다."""
    reservation = _get_cancel_requested_or_400(db, reservation_id)
    reservation.status = "confirmed"
    reservation.cancel_requested_at = None
    reservation.cancel_reason = None
    db.commit()

    villa_notify.notify_cancel_rejected(db, reservation)
    return {"message": "취소 요청을 반려했습니다. 예약이 유지됩니다."}


@router.get("/admin/settings")
def get_villa_admin_settings(
    current_user: models.User = Depends(auth.get_current_villa_manager),
    db: Session = Depends(get_db),
):
    return {"parking_office_email": parking_office_email(db) or ""}


@router.post("/admin/settings")
def update_villa_admin_settings(
    payload: schemas.VillaAdminSettingsUpdate,
    current_user: models.User = Depends(auth.get_current_villa_manager),
    db: Session = Depends(get_db),
):
    """관리실 메일 주소를 저장한다. 빈 값으로 저장하면 주차등록 메일 안내가 나타나지 않는다."""
    email = payload.parking_office_email.strip()
    if email and "@" not in email:
        raise HTTPException(status_code=400, detail="메일 주소 형식이 올바르지 않습니다.")

    settings = get_villa_settings_data(db)
    settings["parking_office_email"] = email
    save_villa_settings_data(db, settings)

    return {"message": "관리실 메일 주소를 저장했습니다.", "parking_office_email": email}


@router.post("/admin/key/{reservation_id}")
def issue_villa_key(
    reservation_id: int,
    payload: schemas.VillaKeyIssue,
    current_user: models.User = Depends(auth.get_current_villa_manager),
    db: Session = Depends(get_db),
):
    """키 불출을 기록한다. 확정된 예약에만 가능하며, 다시 저장하면 회수 기록이 지워지고 재불출로 취급한다."""
    reservation = db.query(models.VillaReservation).filter(
        models.VillaReservation.id == reservation_id
    ).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
    if reservation.status not in BLOCKING_STATUSES:
        raise HTTPException(status_code=400, detail="확정된 예약만 키 불출을 기록할 수 있습니다.")

    key_number = payload.key_number.strip()
    if not key_number:
        raise HTTPException(status_code=400, detail="키번호를 입력해 주세요.")

    reservation.key_number = key_number
    reservation.key_issued_at = datetime.now()
    reservation.key_returned_at = None
    db.commit()

    return {"message": "키 불출을 기록했습니다."}


@router.post("/admin/key-return/{reservation_id}")
def return_villa_key(
    reservation_id: int,
    current_user: models.User = Depends(auth.get_current_villa_manager),
    db: Session = Depends(get_db),
):
    """키 회수 처리. 캘린더의 '키불출' 배지를 클릭하면 호출된다."""
    reservation = db.query(models.VillaReservation).filter(
        models.VillaReservation.id == reservation_id
    ).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
    if not reservation.key_number:
        raise HTTPException(status_code=400, detail="불출된 키가 없습니다.")
    if reservation.key_returned_at is not None:
        raise HTTPException(status_code=400, detail="이미 회수 처리된 키입니다.")

    reservation.key_returned_at = datetime.now()
    db.commit()

    return {"message": "키 회수를 완료했습니다."}


@router.post("/admin/notify/{round_id}")
def notify_round_results(
    round_id: int,
    current_user: models.User = Depends(auth.get_current_villa_manager),
    db: Session = Depends(get_db),
):
    """
    회차 확정 결과를 일괄 통보한다.
    미확정 경합이 남아 있으면 보류한다. 임의 자동 선정은 하지 않는다.
    """
    booking_round = db.query(models.VillaBookingRound).filter(
        models.VillaBookingRound.id == round_id
    ).first()
    if not booking_round:
        raise HTTPException(status_code=404, detail="회차를 찾을 수 없습니다.")

    pending = db.query(models.VillaReservation).filter(
        models.VillaReservation.round_id == round_id,
        models.VillaReservation.status == "applied",
    ).count()
    if pending:
        raise HTTPException(
            status_code=400,
            detail=f"아직 확정되지 않은 신청이 {pending}건 있습니다. 모두 처리한 뒤 통보하세요.",
        )

    # notified_confirmed 플래그로 중복 발송을 막는다.
    targets = db.query(models.VillaReservation).filter(
        models.VillaReservation.round_id == round_id,
        models.VillaReservation.status.in_(("confirmed", "rejected")),
        models.VillaReservation.notified_confirmed == False,
    ).all()

    confirmed_count = 0
    rejected_count = 0
    for reservation in targets:
        if reservation.status == "confirmed":
            villa_notify.notify_confirmed(db, reservation)
            confirmed_count += 1
        else:
            villa_notify.notify_rejected(db, reservation)
            rejected_count += 1
        reservation.notified_confirmed = True

    booking_round.status = "notified"
    db.commit()

    return {
        "message": f"확정 {confirmed_count}건, 미선정 {rejected_count}건을 통보했습니다.",
        "confirmed": confirmed_count,
        "rejected": rejected_count,
    }
