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

ALGORITHM = "HS256"
# 만료 1년은 유출 시 악용 창이 지나치게 길다. 사내 SSO 재로그인은 한 번의
# 리다이렉트로 끝나므로 짧게 잡아도 부담이 적다. 필요하면 이 값만 조정한다.
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

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
    """현재 서명 키로만 검증한다. 다른 키로 서명된 토큰은 위조로 간주해 거부한다."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
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

async def get_current_villa_manager(current_user: models.User = Depends(get_current_user)):
    """
    비트별장 관리 API 전용 게이트. 시스템 전체 관리자(role='admin')는 물론
    별장만 위임받은 담당자(is_villa_admin)도 통과한다. golf/users/smtp 등
    다른 관리 영역은 여전히 get_current_active_admin(전체 관리자)만 허용한다.
    """
    if current_user.role != "admin" and not current_user.is_villa_admin:
        raise HTTPException(status_code=400, detail="비트별장 관리 권한이 없습니다.")
    return current_user
