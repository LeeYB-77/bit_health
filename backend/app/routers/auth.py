from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
from .. import schemas, crud, database
from .. import auth as auth_utils # Use util module

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)

@router.post("/login", response_model=schemas.Token)
async def login_for_access_token(form_data: schemas.LoginRequest, db: Session = Depends(database.get_db)):
    user = crud.get_user_by_name_and_birth(db, name=form_data.name, birth_date=form_data.birth_date)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect name or birth date",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Use ACCESS_TOKEN_EXPIRE_MINUTES from utils
    access_token_expires = timedelta(minutes=auth_utils.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_utils.create_access_token(
        data={"sub": str(user.id), "name": user.name, "role": user.role}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user_name": user.name, "role": user.role}
