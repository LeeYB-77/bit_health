from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from . import schemas, database, models
import os

# JWT 서명 키. 기본값을 두면 소스에 적힌 키로 운영 토큰이 서명되므로 반드시 주입받는다.
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY 환경변수가 설정되지 않았습니다. "
        ".env에 SECRET_KEY를 추가하고 docker-compose가 이를 주입하는지 확인하세요."
    )

# 전환기 전용. 구 서명 키로 발급된 토큰(만료 1년)을 계속 수용해 강제 로그아웃을 막는다.
# 기존 토큰이 자연 교체된 뒤(2~4주) 이 변수와 아래 폴백 로직을 함께 제거해야 한다.
LEGACY_SECRET_KEY = os.getenv("LEGACY_SECRET_KEY")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 365 # 1 year

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    # 발급은 항상 현재 키로만 한다.
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def _decode_token(token: str):
    """현재 키로 검증하고, 실패하면 전환기 레거시 키로 한 번 더 시도한다."""
    keys = [SECRET_KEY]
    if LEGACY_SECRET_KEY:
        keys.append(LEGACY_SECRET_KEY)

    for key in keys:
        try:
            return jwt.decode(token, key, algorithms=[ALGORITHM])
        except JWTError:
            continue
    return None

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = _decode_token(token)
    if payload is None:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
         raise credentials_exception

    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: models.User = Depends(get_current_user)):
    return current_user

async def get_current_active_admin(current_user: models.User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=400, detail="Inactive user or not admin")
    return current_user
