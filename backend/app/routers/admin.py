from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import schemas, crud, models, database
from .. import schemas, crud, models, database, auth
from typing import List, Dict, Any
from datetime import datetime, date, timedelta

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(auth.get_current_active_user)] # Ensure only logged-in users access (can refine to admin only)
)

# Dependency to check for admin role
def get_current_admin(current_user: schemas.User = Depends(auth.get_current_active_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user

@router.get("/dashboard/stats", response_model=Dict[str, int])
def get_dashboard_stats(db: Session = Depends(database.get_db), current_user: schemas.User = Depends(get_current_admin)):
    total_users = db.query(models.User).count()
    
    gym = db.query(models.Facility).filter(models.Facility.type == "gym").first()
    golf = db.query(models.Facility).filter(models.Facility.type == "golf").first()
    
    current_gym_users = 0 
    current_golf_users = 0
    
    if gym:
        current_gym_users = db.query(models.AccessLog).filter(
            models.AccessLog.facility_id == gym.id,
            models.AccessLog.check_out_time == None
        ).count()
        
    if golf:
        current_golf_users = db.query(models.AccessLog).filter(
            models.AccessLog.facility_id == golf.id,
            models.AccessLog.check_out_time == None
        ).count()
        
    return {
        "total_users": total_users,
        "current_gym_users": current_gym_users,
        "current_golf_users": current_golf_users
    }

@router.get("/dashboard/current-users")
def get_current_users(db: Session = Depends(database.get_db), current_user: schemas.User = Depends(get_current_admin)):
    users = []
    
    active_logs = db.query(models.AccessLog).join(models.Facility).filter(
        models.AccessLog.check_out_time == None
    ).all()
    
    for log in active_logs:
        facility_name = "Health" if log.facility.type == "gym" else "Screen Golf"
        users.append({
            "id": log.user.id,
            "name": log.user.name,
            "type": facility_name,
            "enter_time": log.check_in_time
        })
    return users

@router.get("/dashboard/golf-reservations")
def get_golf_reservations(db: Session = Depends(database.get_db), current_user: schemas.User = Depends(get_current_admin)):
    # Placeholder for golf reservations
    return []

@router.post("/golf/available-times")
def set_golf_available_times(times: List[str], db: Session = Depends(database.get_db), current_user: schemas.User = Depends(get_current_admin)):
    # Implementation for setting available times
    # This might need a new model 'GolfSettings' or similar.
    return {"message": "Updated available times", "times": times}

@router.get("/dashboard/usage-history")
def get_usage_history(period: str = "this_week", db: Session = Depends(database.get_db), current_user: schemas.User = Depends(get_current_admin)):
    result = []
    today = date.today()
    
    start_date = today
    end_date = today

    if period == "this_week":
        start_date = today - timedelta(days=today.weekday()) # Monday
        end_date = start_date + timedelta(days=6) # Sunday
    elif period == "last_week":
        start_date = today - timedelta(days=today.weekday() + 7)
        end_date = start_date + timedelta(days=6)
    elif period == "month":
        start_date = today.replace(day=1)
        # Get last day of month
        next_month = today.replace(day=28) + timedelta(days=4)
        end_date = next_month - timedelta(days=next_month.day)
    
    # Calculate total days to iterate
    delta = (end_date - start_date).days + 1
    
    # Pre-fetch all logs for the range to minimize DB queries
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())
    
    all_logs = db.query(models.AccessLog).join(models.Facility).filter(
        models.AccessLog.check_in_time >= start_dt,
        models.AccessLog.check_in_time <= end_dt
    ).all()
    
    # Organize logs by date
    logs_by_date = {}
    for log in all_logs:
        log_date = log.check_in_time.date()
        if log_date not in logs_by_date:
            logs_by_date[log_date] = []
        logs_by_date[log_date].append(log)

    days_kr = ["월", "화", "수", "목", "금", "토", "일"]

    for i in range(delta):
        target_date = start_date + timedelta(days=i)
        
        health_users_set = set()
        golf_users_set = set()
        
        day_logs = logs_by_date.get(target_date, [])
        
        for log in day_logs:
            if log.facility.type == "gym":
                health_users_set.add(log.user.name)
            elif log.facility.type == "golf":
                golf_users_set.add(log.user.name)
        
        day_str = days_kr[target_date.weekday()]
        
        # Determine label based on period
        if period == "month":
            name_label = f"{target_date.day}일"
        else: # weekly
            name_label = f"{target_date.strftime('%m-%d')} ({day_str})"
        
        result.append({
            "name": name_label,
            "date": target_date.strftime("%m-%d"),
            "health": len(health_users_set),
            "golf": len(golf_users_set),
            "health_users": list(health_users_set),
            "golf_users": list(golf_users_set)
        })
        
    return result
