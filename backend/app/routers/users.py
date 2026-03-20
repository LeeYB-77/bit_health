from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import openpyxl
import io
from .. import schemas, crud, auth, models
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel

router = APIRouter(
    prefix="/api/users",
    tags=["users"],
)

@router.post("/upload", status_code=201)
async def upload_users_excel(
    file: UploadFile = File(...), 
    current_user: models.User = Depends(auth.get_current_active_admin),
    db: Session = Depends(auth.get_db)
):
    if not file.filename.endswith(('.xls', '.xlsx')):
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload Excel file.")
    
    contents = await file.read()
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
        sheet = workbook.active
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read Excel file: {str(e)}")
    
    # Expected columns: Name, BirthDate, Department (Role defaults to user)
    # Header check
    headers = [cell.value for cell in sheet[1]]
    required_columns = ['Name', 'BirthDate']
    
    # Simple mapping based on index
    try:
        name_idx = headers.index('Name')
        birth_idx = headers.index('BirthDate')
        dept_idx = headers.index('Department') if 'Department' in headers else -1
    except ValueError:
         raise HTTPException(status_code=400, detail=f"Missing required columns. Expected header row with: {required_columns}")
    
    success_count = 0
    errors = []
    
    # Iterate from 2nd row
    for i, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        try:
            name = str(row[name_idx]).strip() if row[name_idx] is not None else ""
            birth_date = str(row[birth_idx]).strip() if row[birth_idx] is not None else ""
            
            if not name or not birth_date:
                continue

            department = None
            if dept_idx != -1 and row[dept_idx] is not None:
                department = str(row[dept_idx]).strip()

            # Basic validation
            if len(birth_date) != 6: # YYYYMMDD -> YYMMDD (6 digits)
                 errors.append(f"Row {i}: Invalid birth date format for {name} (expected 6 digits)")
                 continue

            # Check if user exists
            existing_user = crud.get_user_by_name_and_birth(db, name=name, birth_date=birth_date)
            if existing_user:
                continue
            
            user_create = schemas.UserCreate(name=name, birth_date=birth_date, department=department, role="user")
            crud.create_user(db, user_create)
            success_count += 1
            
        except Exception as e:
            errors.append(f"Row {i}: Error creating user - {str(e)}")
            
    return {"message": f"Successfully imported {success_count} users.", "errors": errors}

@router.get("/me", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(auth.get_current_user)):
    return current_user

@router.get("/", response_model=List[schemas.User])
def read_users(
    skip: int = 0, 
    limit: int = 1000, 
    db: Session = Depends(auth.get_db), 
    current_user: models.User = Depends(auth.get_current_active_admin)
):
    users = crud.get_users(db, skip=skip, limit=limit)
    return users

@router.post("/", response_model=schemas.User, status_code=201)
def create_user(
    user: schemas.UserCreate, 
    db: Session = Depends(auth.get_db), 
    current_user: models.User = Depends(auth.get_current_active_admin)
):
    db_user = crud.get_user_by_name_and_birth(db, name=user.name, birth_date=user.birth_date)
    if db_user:
        raise HTTPException(status_code=400, detail="User already registered")
    
    # Validate birth date format (YYMMDD) - simplistic check
    if len(user.birth_date) != 6 or not user.birth_date.isdigit():
        raise HTTPException(status_code=400, detail="Birth date must be 6 digits (YYMMDD)")
        
    return crud.create_user(db=db, user=user)

@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int, 
    db: Session = Depends(auth.get_db), 
    current_user: models.User = Depends(auth.get_current_active_admin)
):
    success = crud.delete_user(db, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return None

class RoleUpdate(BaseModel):
    role: str

@router.put("/{user_id}/role", response_model=schemas.User)
def update_user_role(
    user_id: int, 
    role_update: RoleUpdate,
    db: Session = Depends(auth.get_db), 
    current_user: models.User = Depends(auth.get_current_active_admin)
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="자기 자신의 권한은 변경할 수 없습니다.")
        
    if role_update.role not in ["user", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = role_update.role
    db.commit()
    db.refresh(user)
    return user

@router.get("/me/dashboard")
def get_user_dashboard_stats(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(auth.get_db)
):
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    start_of_month = datetime(now.year, now.month, 1, tzinfo=KST)
    
    # 1. Monthly Exercise Count (Gym Access + Golf Access)
    # We count unique days or total access logs? Request says "Exercise Count". Logs are simplest.
    # Note: AccessLog includes both Gym and Golf.
    
    monthly_count = db.query(models.AccessLog).filter(
        models.AccessLog.user_id == current_user.id,
        models.AccessLog.check_in_time >= start_of_month
    ).count()
    
    # 2. Today's Golf Reservation
    start_of_day = datetime(now.year, now.month, now.day, tzinfo=KST)
    end_of_day = start_of_day + timedelta(days=1)
    
    golf_facility = db.query(models.Facility).filter(models.Facility.type == "golf").first()
    has_today_reservation = False
    
    if golf_facility:
        reservation = db.query(models.Reservation).filter(
            models.Reservation.user_id == current_user.id,
            models.Reservation.facility_id == golf_facility.id,
            models.Reservation.status == "reserved",
            models.Reservation.start_time >= start_of_day,
            models.Reservation.start_time < end_of_day
        ).first()
        if reservation:
            has_today_reservation = True
            
    return {
        "monthly_count": monthly_count,
        "has_today_reservation": has_today_reservation
    }
