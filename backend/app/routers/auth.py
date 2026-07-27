from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta
import os
import requests
import jwt as pyjwt
from pydantic import BaseModel
from .. import schemas, crud, database
from .. import auth as auth_utils # Use util module

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"],
)

# 관리자 계정은 SSO 이메일로 지정한다(콤마 구분). 이름으로 판정하면 동명이인이
# 로그인할 때 관리자 권한을 얻는다.
ADMIN_EMAILS = {
    e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()
}

@router.post("/login", response_model=schemas.Token)
async def login_for_access_token(form_data: schemas.LoginRequest, db: Session = Depends(database.get_db)):
    user = crud.get_user_by_name_and_birth(db, name=form_data.name, birth_date=form_data.birth_date)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect name or birth date",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=auth_utils.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_utils.create_access_token(
        data={"sub": str(user.id), "name": user.name, "role": user.role}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user_name": user.name, "role": user.role}

class SSOLoginRequest(BaseModel):
    code: str
    redirect_uri: str

@router.post("/sso-login", response_model=schemas.Token)
async def sso_login(req: SSOLoginRequest, db: Session = Depends(database.get_db)):
    resp = requests.post("https://drive.bit.kr/auth/token", data={
        "code": req.code,
        "redirect_uri": req.redirect_uri,
        "client_id": "bit_health",
        "client_secret": ""
    })
    
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to exchange code")
    
    tokens = resp.json()
    id_token = tokens.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="No id_token received")
    
    jwks_url = "https://drive.bit.kr/auth/jwks"
    jwks_client = pyjwt.PyJWKClient(jwks_url)
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        payload = pyjwt.decode(
            id_token, 
            signing_key.key, 
            algorithms=["RS256"], 
            issuer="https://drive.bit.kr/auth",
            audience="bit_health"
        )
    except Exception as e:
        # If audience fails in decode, try again without audience
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)
            payload = pyjwt.decode(
                id_token, 
                signing_key.key, 
                algorithms=["RS256"], 
                issuer="https://drive.bit.kr/auth",
                options={"verify_aud": False}
            )
        except Exception as e2:
            raise HTTPException(status_code=400, detail=f"Token verification failed: {e2}")
        
    sub = payload.get("sub")
    email = payload.get("email")
    name = payload.get("name")
    
    if not sub:
        raise HTTPException(status_code=400, detail="Invalid token payload")
        
    is_admin_email = bool(email) and email.lower() in ADMIN_EMAILS
    role = "admin" if is_admin_email else "user"

    user = crud.get_user_by_sub(db, sub=sub)
    is_new_user = False
    if not user:
        is_new_user = True
        user_create = schemas.UserCreate(
            name=name or "SSO User",
            email=email,
            sub=sub,
            role=role
        )
        user = crud.create_user_sso(db, user_create)
    elif is_admin_email and user.role != "admin":
        # 승격만 하고 강등하지 않는다. /api/users/{id}/role로 수동 부여한 권한이 유지되고,
        # ADMIN_EMAILS 설정이 잘못돼도 관리자 접근을 잃지 않는다.
        user.role = "admin"
        db.commit()

    access_token_expires = timedelta(minutes=auth_utils.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_utils.create_access_token(
        data={"sub": str(user.id), "name": user.name, "role": user.role}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user_name": user.name, "role": user.role, "is_new_user": is_new_user}
