# 테스트 전역 픽스처: SQLite 인메모리 DB, 시설 시드, 인증 클라이언트를 제공
import os

# app 패키지 import 이전에 반드시 설정해야 한다.
# - database.py는 import 시점에 DATABASE_URL을 읽는다.
# - main.py는 import 시점에 Base.metadata.create_all()을 호출한다.
# 따라서 미리 sqlite로 지정하지 않으면 테스트가 PostgreSQL 접속을 시도하며 실패한다.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_pytest")
# 전환기 레거시 키 폴백을 검증하기 위해 테스트에서도 설정한다.
os.environ.setdefault("LEGACY_SECRET_KEY", "legacy_test_secret_key_for_pytest")
os.environ.setdefault("ADMIN_EMAILS", "boss@bit.kr, second-admin@bit.kr")
# Slack 토큰이 개발자 셸에 남아 있으면 테스트가 외부 API를 호출하게 된다. 확실히 제거한다.
os.environ.pop("SLACK_BOT_TOKEN", None)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth as auth_utils
from app import database, models
from app.main import app

# TestClient는 요청을 별도 스레드에서 처리한다. 동일한 인메모리 DB를 공유하려면
# StaticPool로 단일 커넥션을 고정하고 check_same_thread를 끈다.
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db():
    models.Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        models.Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    # get_db가 database.py와 auth.py 두 곳에 중복 정의되어 있고 라우터가 서로 다른 쪽을
    # import한다(gym/golf/admin은 database, users는 auth). 양쪽을 모두 덮어써야 한다.
    app.dependency_overrides[database.get_db] = override_get_db
    app.dependency_overrides[auth_utils.get_db] = override_get_db
    # 컨텍스트 매니저로 열지 않으면 lifespan이 실행되지 않아 APScheduler가 기동되지 않는다.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def facilities(db):
    """initial_data.py와 동일한 시설 구성을 시드한다."""
    gym = models.Facility(name="Gym", type="gym", capacity=15)
    golf = models.Facility(name="ScreenGolf", type="golf", capacity=1)
    db.add_all([gym, golf])
    db.commit()
    db.refresh(gym)
    db.refresh(golf)
    return {"gym": gym, "golf": golf}


@pytest.fixture
def make_user(db):
    counter = {"n": 0}

    def _make(name=None, role="user", birth_date=None, sub=None, email=None, department=None):
        counter["n"] += 1
        n = counter["n"]
        user = models.User(
            name=name if name is not None else f"테스터{n}",
            role=role,
            birth_date=birth_date,
            sub=sub,
            email=email,
            department=department,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def auth_headers():
    def _headers(user):
        token = auth_utils.create_access_token(
            {"sub": str(user.id), "name": user.name, "role": user.role}
        )
        return {"Authorization": f"Bearer {token}"}

    return _headers
