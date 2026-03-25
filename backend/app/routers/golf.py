from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, time
import json
import holidays
from .. import models, auth, schemas
from ..database import get_db
from .. import slack_utils

router = APIRouter(
    prefix="/api/golf",
    tags=["golf"],
    responses={404: {"detail": "Not found"}},
)

PRIORITY_LABELS = {1: "최우선", 2: "우선", 3: "양보"}
PREEMPT_WINDOW_HOURS = 3  # 타인 예약 교체 가능 시간 (시간 전까지)

def get_golf_settings_data(db: Session):
    default_settings = {
        "weekday_slots": [
            {"start": "10:00", "end": "12:00"},
            {"start": "14:00", "end": "16:00"},
            {"start": "19:00", "end": "21:00"}
        ],
        "weekend_start": 9,
        "weekend_end": 18
    }
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "golf_settings").first()
    if setting:
        return json.loads(setting.value)
    else:
        return default_settings


def check_and_apply_no_show_penalty(user: models.User, db: Session):
    """
    사용자의 과거 예약 중 미사용(no-show) 예약이 있는지 확인하고,
    있다면 1개월 예약 정지 패널티를 적용한다.
    no-show 조건: status='reserved' 이고 end_time이 현재보다 과거인 예약 중
                  해당 시간대에 AccessLog 입실 기록이 없는 경우
    """
    now = datetime.now()
    golf = db.query(models.Facility).filter(models.Facility.type == "golf").first()
    if not golf:
        return

    # 과거 예약 중 아직 'reserved' 상태인 것 (completed/canceled 아닌 것)
    past_reserved = db.query(models.Reservation).filter(
        models.Reservation.user_id == user.id,
        models.Reservation.facility_id == golf.id,
        models.Reservation.status == "reserved",
        models.Reservation.end_time < now
    ).all()

    for res in past_reserved:
        # 해당 예약 시간대에 입실 기록이 있는지 확인
        access_log = db.query(models.AccessLog).filter(
            models.AccessLog.user_id == user.id,
            models.AccessLog.facility_id == golf.id,
            models.AccessLog.check_in_time >= res.start_time,
            models.AccessLog.check_in_time <= res.end_time
        ).first()

        if not access_log:
            # no-show: status를 no_show로 변경하고 패널티 적용
            res.status = "no_show"
            suspended_until = now + timedelta(days=30)
            if not user.golf_suspended_until or user.golf_suspended_until < suspended_until:
                user.golf_suspended_until = suspended_until
        else:
            # 사용한 경우 completed로 표시
            res.status = "completed"

    db.commit()


@router.get("/slots")
def get_available_slots(
    date: str,  # YYYY-MM-DD
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    golf = db.query(models.Facility).filter(models.Facility.type == "golf").first()
    if not golf:
        return {"message": "Golf facility not initialized"}

    settings = get_golf_settings_data(db)

    kr_holidays = holidays.KR()
    is_holiday = target_date in kr_holidays
    weekday = target_date.weekday()  # 0=Mon, 6=Sun

    weekday_slots = settings.get("weekday_slots", [])
    weekend_start = settings.get("weekend_start", 9)
    weekend_end = settings.get("weekend_end", 18)

    slots = []

    start_of_day = datetime.combine(target_date, time.min)
    end_of_day = datetime.combine(target_date, time.max)

    existing_reservations = db.query(models.Reservation).filter(
        models.Reservation.facility_id == golf.id,
        models.Reservation.status == "reserved",
        models.Reservation.start_time >= start_of_day,
        models.Reservation.start_time <= end_of_day
    ).all()

    now = datetime.now()

    def build_slot_info(s_time: str, e_time: str, slot_type: str, index: int):
        try:
            sh, sm = map(int, s_time.split(':'))
            eh, em = map(int, e_time.split(':'))
            start_dt = datetime.combine(target_date, time(sh, sm))
            end_dt = datetime.combine(target_date, time(eh, em))
        except ValueError:
            return None

        # 겹치는 예약 찾기
        taken_res = None
        for res in existing_reservations:
            if (start_dt < res.end_time) and (end_dt > res.start_time):
                taken_res = res
                break

        taken_by_priority = taken_res.priority if taken_res else None
        taken_by_user_id = taken_res.user_id if taken_res else None
        taken_res_id = taken_res.id if taken_res else None

        # 내 우선순위보다 낮은 우선순위(숫자 큰 것)가 예약 중이면 교체 가능 여부 계산
        # - taken_by_priority > current? → 교체 가능 후보
        # - 3시간 전 체크: start_dt - now >= 3h
        can_preempt = False
        if taken_res and taken_by_user_id != current_user.id:
            # 우선순위 교체 가능 조건: 내 숫자 < 상대 숫자
            # (나중에 예약 시 priority를 알아야 하므로 프론트에서 선택한 값 기준이지만
            #  슬롯 조회 단계에서는 "교체 가능 후보 슬롯"임을 알려주기 위해
            #  taken_by_priority가 있으면 교체 가능 여부 플래그를 제공)
            time_until_start = (start_dt - now).total_seconds() / 3600
            if time_until_start >= PREEMPT_WINDOW_HOURS:
                can_preempt = True  # 실제 교체 가능 여부는 예약 시점에 priority 비교로 결정

        return {
            "id": index,
            "time": s_time,
            "end_time": e_time,
            "available": taken_res is None,
            "type": slot_type,
            "taken_by_priority": taken_by_priority,
            "taken_res_id": taken_res_id,
            "can_preempt": can_preempt,  # 3시간 전 조건 충족 여부
        }

    if weekday >= 5 or is_holiday:
        current_hour = weekend_start
        idx = 0
        while current_hour < weekend_end:
            s_time = f"{current_hour:02d}:00"
            e_time = f"{current_hour + 1:02d}:00"
            info = build_slot_info(s_time, e_time, "weekend", idx)
            if info:
                slots.append(info)
            current_hour += 1
            idx += 1
    else:
        for i, slot_def in enumerate(weekday_slots):
            if isinstance(slot_def, str):
                try:
                    h, m = map(int, slot_def.split(':'))
                    start_dt = datetime.combine(target_date, time(h, m))
                    end_dt = start_dt + timedelta(hours=2)
                    s_time = slot_def
                    e_time = end_dt.strftime("%H:%M")
                except Exception:
                    continue
            else:
                s_time = slot_def["start"]
                e_time = slot_def["end"]

            info = build_slot_info(s_time, e_time, "weekday", i)
            if info:
                slots.append(info)

    return slots


@router.post("/reserve", response_model=schemas.Reservation)
def create_reservation(
    reservation_in: schemas.ReservationCreate,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    golf = db.query(models.Facility).filter(models.Facility.type == "golf").first()
    if not golf:
        raise HTTPException(status_code=404, detail="Golf facility not found")

    now = datetime.now()
    start_dt = reservation_in.start_time
    end_dt = reservation_in.end_time
    priority = reservation_in.priority

    if priority not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="우선순위는 1(최우선), 2(우선), 3(양보) 중 하나여야 합니다.")

    if start_dt >= end_dt:
        raise HTTPException(status_code=400, detail="종료 시간은 시작 시간 이후여야 합니다.")

    # 2인 이상 예약 시 동반자 필수
    if reservation_in.participant_count > 1:
        if not reservation_in.companions or not reservation_in.companions.strip():
            raise HTTPException(status_code=400, detail="2인 이상 예약 시 동반자 정보는 필수입니다.")

    # 미사용 패널티 기능 임시 중단 (사용자 요청)
    # check_and_apply_no_show_penalty(current_user, db)
    # db.refresh(current_user)

    # 예약 정지 체크 (임시 중단)
    # if current_user.golf_suspended_until and current_user.golf_suspended_until > now:
    #     suspended_str = current_user.golf_suspended_until.strftime("%Y년 %m월 %d일")
    #     raise HTTPException(
    #         status_code=403,
    #         detail=f"미사용 패널티로 인해 {suspended_str}까지 예약이 불가합니다."
    #     )

    # 겹치는 기존 예약 확인 (다중 시간 가능성)
    existing_list = db.query(models.Reservation).filter(
        models.Reservation.facility_id == golf.id,
        models.Reservation.status == "reserved",
        models.Reservation.start_time < end_dt,
        models.Reservation.end_time > start_dt
    ).all()

    if existing_list:
        # 1차: 모든 기존 예약에 대해 교체 권한 검증
        for existing in existing_list:
            # 본인 예약인 경우
            if existing.user_id == current_user.id:
                raise HTTPException(status_code=400, detail="본인이 이미 해당 시간대에 예약하셨습니다.")

            # 타인 예약 교체 가능 여부 판단
            # 우선순위: 숫자 낮을수록 높음 (1 > 2 > 3)
            if priority >= existing.priority:
                priority_label = PRIORITY_LABELS.get(existing.priority, str(existing.priority))
                raise HTTPException(
                    status_code=409,
                    detail=f"해당 시간대 일부가 '{priority_label}' 등급으로 이미 예약되어 있습니다. 더 높은 우선순위만 교체할 수 있습니다."
                )

            # 3시간 전 체크
            hours_until = (existing.start_time - now).total_seconds() / 3600
            if hours_until < PREEMPT_WINDOW_HOURS:
                raise HTTPException(
                    status_code=400,
                    detail=f"타인의 예약을 교체하려면 시작 {PREEMPT_WINDOW_HOURS}시간 전까지만 가능합니다."
                )

        # 2차: 모든 검증을 통과했다면 기존 예약 전부 취소 처리 및 개별 알림 발송
        for existing in existing_list:
            existing.status = "canceled"
            
            # Slack 알림 쏘기 (기존 예약자에게)
            if existing.user and existing.user.email:
                start_time_str = existing.start_time.strftime("%Y-%m-%d %H:%M")
                new_priority_label = PRIORITY_LABELS.get(priority, "최우선")
                try:
                    slack_utils.notify_reservation_preempted(
                        email=existing.user.email,
                        old_start_time=start_time_str,
                        new_user_name=current_user.name,
                        new_priority=new_priority_label
                    )
                except Exception as e:
                    print(f"Failed to send slack message: {e}")

        db.commit()

    # 새 예약 생성
    db_reservation = models.Reservation(
        user_id=current_user.id,
        facility_id=golf.id,
        start_time=start_dt,
        end_time=end_dt,
        participant_count=reservation_in.participant_count,
        companions=reservation_in.companions,
        status="reserved",
        priority=priority
    )
    db.add(db_reservation)
    db.commit()
    db.refresh(db_reservation)
    return db_reservation


@router.post("/cancel/{reservation_id}")
def cancel_reservation(
    reservation_id: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    reservation = db.query(models.Reservation).filter(models.Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Reservation not found")

    if reservation.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    reservation.status = "canceled"
    db.commit()
    return {"message": "Reservation canceled"}


@router.get("/my")
def get_my_reservations(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    today = datetime.now().date()
    start_of_day = datetime.combine(today, time.min)

    return db.query(models.Reservation).filter(
        models.Reservation.user_id == current_user.id,
        models.Reservation.start_time >= start_of_day
    ).order_by(models.Reservation.start_time.asc()).all()


@router.post("/access")
def access_golf(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Toggle golf access: Check-in if out, Check-out if in.
    입실 기록은 미사용 패널티 판단에 활용됩니다.
    """
    golf = db.query(models.Facility).filter(models.Facility.type == "golf").first()
    if not golf:
        raise HTTPException(status_code=404, detail="Golf facility not found")

    existing_log = db.query(models.AccessLog).filter(
        models.AccessLog.user_id == current_user.id,
        models.AccessLog.facility_id == golf.id,
        models.AccessLog.check_out_time == None
    ).first()

    if existing_log:
        existing_log.check_out_time = datetime.now()
        db.commit()
        return {"status": "out", "message": "스크린골프 퇴실 처리되었습니다."}
    else:
        new_log = models.AccessLog(
            user_id=current_user.id,
            facility_id=golf.id,
            check_in_time=datetime.now()
        )
        db.add(new_log)
        db.commit()
        return {"status": "in", "message": "스크린골프 입실 처리되었습니다."}


# --- Admin & Settings ---

@router.get("/settings")
def get_golf_settings(
    current_user: models.User = Depends(auth.get_current_active_admin),
    db: Session = Depends(get_db)
):
    return get_golf_settings_data(db)


@router.post("/settings")
def update_golf_settings(
    settings: dict,
    current_user: models.User = Depends(auth.get_current_active_admin),
    db: Session = Depends(get_db)
):
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == "golf_settings").first()
    if setting:
        setting.value = json.dumps(settings)
    else:
        new_setting = models.SystemSetting(key="golf_settings", value=json.dumps(settings))
        db.add(new_setting)

    db.commit()
    return {"message": "Settings updated"}


@router.get("/admin/reservations")
def get_all_reservations(
    date: str = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_admin)
):
    golf = db.query(models.Facility).filter(models.Facility.type == "golf").first()
    query = db.query(models.Reservation)

    if golf:
        query = query.filter(models.Reservation.facility_id == golf.id)

    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
            start_of_day = datetime.combine(target_date, time.min)
            end_of_day = datetime.combine(target_date, time.max)
            query = query.filter(
                models.Reservation.start_time >= start_of_day,
                models.Reservation.start_time <= end_of_day
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")

    reservations = query.order_by(models.Reservation.start_time).all()

    result = []
    for res in reservations:
        user_name = res.user.name if res.user else "Unknown"
        user_dept = res.user.department if res.user else ""

        result.append({
            "id": res.id,
            "start_time": res.start_time,
            "end_time": res.end_time,
            "participant_count": res.participant_count,
            "companions": res.companions,
            "status": res.status,
            "priority": res.priority,
            "user_name": user_name,
            "user_dept": user_dept
        })
    return result
