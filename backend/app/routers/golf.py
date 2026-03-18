from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, time
import json
import holidays
from .. import models, auth, schemas
from ..database import get_db

router = APIRouter(
    prefix="/api/golf",
    tags=["golf"],
    responses={404: {"detail": "Not found"}},
)

def get_golf_settings_data(db: Session):
    # Default settings
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

@router.get("/slots")
def get_available_slots(
    date: str, # YYYY-MM-DD
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
    weekday = target_date.weekday() # 0=Mon, 6=Sun
    
    # Defaults
    weekday_slots = settings.get("weekday_slots", [])
    weekend_start = settings.get("weekend_start", 9)
    weekend_end = settings.get("weekend_end", 18)

    slots = []
    
    # Get reservations
    start_of_day = datetime.combine(target_date, time.min)
    end_of_day = datetime.combine(target_date, time.max)
    
    existing_reservations = db.query(models.Reservation).filter(
        models.Reservation.facility_id == golf.id,
        models.Reservation.status == "reserved",
        models.Reservation.start_time >= start_of_day,
        models.Reservation.start_time <= end_of_day
    ).all()

    if weekday >= 5 or is_holiday: # Weekend or Holiday
        # Interval based (1 hour chunks for now, but UI can allow custom duration if needed)
        # For simplicity, let's offer 1-hour slots that can be combined or selected as start time.
        # Requirements said: "Users can set start/end time". 
        # API will return available *hours*. Frontend handles range selection.
        
        current_hour = weekend_start
        while current_hour < weekend_end:
            slot_start = datetime.combine(target_date, time(current_hour, 0))
            slot_end = slot_start + timedelta(hours=1) # Minimal unit 
            
            # Check overlap
            is_taken = False
            for res in existing_reservations:
                # Overlap logic: (StartA < EndB) and (EndA > StartB)
                if (slot_start < res.end_time) and (slot_end > res.start_time):
                    is_taken = True
                    break
            
            slots.append({
                "time": slot_start.strftime("%H:%M"),
                "end_time": slot_end.strftime("%H:%M"),
                "available": not is_taken,
                "type": "weekend" # hourly
            })
            current_hour += 1
            
    else: # Weekday (Fixed Slots)
        for i, slot_def in enumerate(weekday_slots):
            # slot_def might be string "10:00" (old) or dict (new)
            if isinstance(slot_def, str):
                s_time = slot_def
                # Estimating end time +1 hour if old format
                try:
                    h, m = map(int, s_time.split(':'))
                    start_dt = datetime.combine(target_date, time(h, m))
                    end_dt = start_dt + timedelta(hours=2) # Default 2 hours if not specified? 
                    e_time = end_dt.strftime("%H:%M")
                except:
                    continue
            else:
                s_time = slot_def["start"]
                e_time = slot_def["end"]
            
            try:
                sh, sm = map(int, s_time.split(':'))
                eh, em = map(int, e_time.split(':'))
                start_dt = datetime.combine(target_date, time(sh, sm))
                end_dt = datetime.combine(target_date, time(eh, em))
                
                is_taken = False
                for res in existing_reservations:
                    if (start_dt < res.end_time) and (end_dt > res.start_time):
                        is_taken = True
                        break

                slots.append({
                    "id": i,
                    "time": s_time,
                    "end_time": e_time,
                    "available": not is_taken,
                    "type": "weekday" # fixed
                })
            except ValueError:
                continue

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
        
    start_dt = reservation_in.start_time
    end_dt = reservation_in.end_time
    
    if start_dt >= end_dt:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    # Check overlaps
    existing = db.query(models.Reservation).filter(
        models.Reservation.facility_id == golf.id,
        models.Reservation.status == "reserved",
        models.Reservation.start_time < end_dt,
        models.Reservation.end_time > start_dt
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Selected time slot overlaps with an existing reservation")
        
    db_reservation = models.Reservation(
        user_id=current_user.id,
        facility_id=golf.id,
        start_time=start_dt,
        end_time=end_dt,
        participant_count=reservation_in.participant_count,
        companions=reservation_in.companions,
        status="reserved"
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
    # Hide past reservations (keep today's)
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
    """
    golf = db.query(models.Facility).filter(models.Facility.type == "golf").first()
    if not golf:
        raise HTTPException(status_code=404, detail="Golf facility not found")

    # Check current status
    existing_log = db.query(models.AccessLog).filter(
        models.AccessLog.user_id == current_user.id,
        models.AccessLog.facility_id == golf.id,
        models.AccessLog.check_out_time == None
    ).first()

    if existing_log:
        # Check-out
        existing_log.check_out_time = datetime.now()
        db.commit()
        return {"status": "out", "message": "스크린골프 퇴실 처리되었습니다."}
    else:
        # Check-in
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
        # Use relationship now available in models
        user_name = res.user.name if res.user else "Unknown"
        user_dept = res.user.department if res.user else "" 
        
        result.append({
            "id": res.id,
            "start_time": res.start_time,
            "end_time": res.end_time,
            "participant_count": res.participant_count,
            "companions": res.companions,
            "status": res.status,
            "user_name": user_name,
            "user_dept": user_dept
        })
    return result
