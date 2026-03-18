from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from .. import models, auth
from ..database import get_db

router = APIRouter(
    prefix="/api/gym",
    tags=["gym"],
    responses={404: {"detail": "Not found"}},
)

@router.get("/status")
def get_gym_status(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get current gym status: active user count, congestion level, and my status.
    """
    # Find Gym facility
    gym = db.query(models.Facility).filter(models.Facility.type == "gym").first()
    if not gym:
        # If facility data is missing, return default safe values
        return {
            "count": 0, 
            "congestion": "low", 
            "my_status": "out", 
            "capacity": 30,
            "message": "Gym facility not initialized"
        }
    
    # Count active users (checked in but not checked out)
    active_count = db.query(models.AccessLog).filter(
        models.AccessLog.facility_id == gym.id,
        models.AccessLog.check_out_time == None
    ).count()

    # Check if current user is checked in
    my_log = db.query(models.AccessLog).filter(
        models.AccessLog.user_id == current_user.id,
        models.AccessLog.facility_id == gym.id,
        models.AccessLog.check_out_time == None
    ).first()

    my_status = "in" if my_log else "out"
    
    # Calculate congestion
    capacity = gym.capacity if gym.capacity else 30
    congestion = "low"
    if active_count >= capacity * 0.8:
        congestion = "high"
    elif active_count >= capacity * 0.5:
        congestion = "medium"

    return {
        "count": active_count, 
        "congestion": congestion, 
        "my_status": my_status, 
        "capacity": capacity
    }

@router.post("/access")
def access_gym(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Toggle gym access: Check-in if out, Check-out if in.
    """
    gym = db.query(models.Facility).filter(models.Facility.type == "gym").first()
    if not gym:
        raise HTTPException(status_code=404, detail="Gym facility not found")

    # Check current status
    existing_log = db.query(models.AccessLog).filter(
        models.AccessLog.user_id == current_user.id,
        models.AccessLog.facility_id == gym.id,
        models.AccessLog.check_out_time == None
    ).first()

    if existing_log:
        # Check-out
        existing_log.check_out_time = datetime.now()
        db.commit()
        return {"status": "out", "message": "퇴실 처리되었습니다."}
    else:
        # Check-in
        # Validate capacity (Optional strict check)
        # active_count = db.query(models.AccessLog)...
        
        new_log = models.AccessLog(
            user_id=current_user.id,
            facility_id=gym.id,
            check_in_time=datetime.now()
        )
        db.add(new_log)
        db.commit()
        return {"status": "in", "message": "입실 처리되었습니다."}
