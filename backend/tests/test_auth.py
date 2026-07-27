# SSO 로그인 처리와 JWT 발급/검증(전환기 이중 키 포함)의 동작을 고정하는 테스트
from datetime import datetime, timedelta

import pytest
from jose import JWTError
from jose import jwt as jose_jwt

from app import auth as auth_utils
from app import models
from app.routers import auth as auth_router


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


@pytest.fixture
def mock_sso(monkeypatch):
    """외부 SSO 서버(drive.bit.kr) 호출과 JWKS 서명 검증을 대체한다."""

    def _apply(sub="sso-uuid-1", email="user@bit.kr", name="김직원", token_status=200):
        def fake_post(url, data=None, **kwargs):
            if token_status != 200:
                return _FakeResponse({}, status_code=token_status)
            return _FakeResponse({"id_token": "fake.id.token"})

        class _FakeSigningKey:
            key = "fake-signing-key"

        class _FakeJWKClient:
            def __init__(self, url):
                pass

            def get_signing_key_from_jwt(self, token):
                return _FakeSigningKey()

        monkeypatch.setattr(auth_router.requests, "post", fake_post)
        monkeypatch.setattr(auth_router.pyjwt, "PyJWKClient", _FakeJWKClient)
        monkeypatch.setattr(
            auth_router.pyjwt,
            "decode",
            lambda *a, **kw: {"sub": sub, "email": email, "name": name},
        )

    return _apply


def _sso_login(client):
    return client.post(
        "/api/auth/sso-login",
        json={"code": "auth-code", "redirect_uri": "https://book.bit.kr/login/callback"},
    )


def test_sso_신규사용자_생성(client, db, mock_sso):
    mock_sso(sub="sso-uuid-new", email="new@bit.kr", name="신입사원")

    res = _sso_login(client)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["user_name"] == "신입사원"
    assert body["role"] == "user"
    assert body["is_new_user"] is True

    user = db.query(models.User).filter(models.User.sub == "sso-uuid-new").one()
    assert user.email == "new@bit.kr"
    assert user.birth_date is None  # SSO 사용자는 생년월일이 없다


def test_sso_기존사용자_재로그인(client, db, mock_sso, make_user):
    existing = make_user(name="김직원", sub="sso-uuid-1", email="user@bit.kr")
    mock_sso(sub="sso-uuid-1", email="user@bit.kr", name="김직원")

    res = _sso_login(client)
    assert res.status_code == 200
    assert res.json()["is_new_user"] is False
    assert db.query(models.User).count() == 1

    payload = jose_jwt.decode(
        res.json()["access_token"], auth_utils.SECRET_KEY, algorithms=[auth_utils.ALGORITHM]
    )
    assert payload["sub"] == str(existing.id)


def test_sso_토큰교환_실패시_400(client, mock_sso):
    mock_sso(token_status=401)
    assert _sso_login(client).status_code == 400


def test_sso_id_token_없으면_400(client, monkeypatch):
    monkeypatch.setattr(
        auth_router.requests, "post", lambda *a, **kw: _FakeResponse({"access_token": "x"})
    )
    res = _sso_login(client)
    assert res.status_code == 400
    assert "id_token" in res.json()["detail"]


def test_sso_sub_없으면_400(client, mock_sso):
    mock_sso(sub=None)
    assert _sso_login(client).status_code == 400


def test_sso_관리자는_ADMIN_EMAILS_기준으로_판정(client, db, mock_sso):
    mock_sso(sub="sso-uuid-admin", email="boss@bit.kr", name="이영배")
    res = _sso_login(client)
    assert res.status_code == 200
    assert res.json()["role"] == "admin"


def test_sso_이메일_대소문자_무시(client, mock_sso):
    mock_sso(sub="sso-uuid-admin2", email="BOSS@BIT.KR", name="이영배")
    assert _sso_login(client).json()["role"] == "admin"


def test_sso_목록에_없는_이메일은_일반사용자(client, mock_sso):
    mock_sso(sub="sso-uuid-2", email="other@bit.kr", name="박사원")
    assert _sso_login(client).json()["role"] == "user"


def test_sso_동명이인은_관리자가_되지_않음(client, db, mock_sso, make_user):
    """
    이전에는 name == "이영배"로 판정해, 같은 이름의 신규 SSO 사용자가
    관리자 권한을 얻었다. 이메일 기준으로 바뀌어 차단된다.
    """
    make_user(name="이영배", role="admin", sub="sso-uuid-real-admin", email="boss@bit.kr")

    mock_sso(sub="sso-uuid-impostor", email="impostor@bit.kr", name="이영배")
    res = _sso_login(client)
    assert res.status_code == 200
    assert res.json()["role"] == "user"

    impostor = db.query(models.User).filter(models.User.sub == "sso-uuid-impostor").one()
    assert impostor.role == "user"


def test_sso_이메일이_없으면_일반사용자(client, mock_sso):
    """SSO payload에 email이 없는 경우에도 안전하게 user로 처리된다."""
    mock_sso(sub="sso-uuid-noemail", email=None, name="이영배")
    assert _sso_login(client).json()["role"] == "user"


def test_sso_기존사용자를_관리자로_승격(client, db, mock_sso, make_user):
    user = make_user(name="승진자", role="user", sub="sso-uuid-promote", email="boss@bit.kr")
    mock_sso(sub="sso-uuid-promote", email="boss@bit.kr", name="승진자")

    assert _sso_login(client).json()["role"] == "admin"
    db.refresh(user)
    assert user.role == "admin"


def test_sso_기존_관리자를_강등하지_않음(client, db, mock_sso, make_user):
    """
    ADMIN_EMAILS에 없어도 DB의 admin 권한은 유지된다.
    설정 실수로 관리자 접근을 잃지 않게 하는 안전장치다.
    """
    admin = make_user(name="수동관리자", role="admin", sub="sso-uuid-manual", email="manual@bit.kr")
    mock_sso(sub="sso-uuid-manual", email="manual@bit.kr", name="수동관리자")

    assert _sso_login(client).json()["role"] == "admin"
    db.refresh(admin)
    assert admin.role == "admin"


def test_토큰으로_내정보_조회(client, make_user, auth_headers):
    user = make_user(name="조회대상", department="관리팀")
    res = client.get("/api/users/me", headers=auth_headers(user))
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "조회대상"
    assert body["department"] == "관리팀"


def test_토큰없으면_401(client):
    assert client.get("/api/users/me").status_code == 401


def test_손상된_토큰은_401(client):
    assert client.get("/api/users/me", headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401


def test_다른_키로_서명한_토큰은_401(client, make_user):
    user = make_user()
    forged = jose_jwt.encode(
        {"sub": str(user.id), "name": user.name, "role": user.role},
        "완전히-다른-키",
        algorithm=auth_utils.ALGORITHM,
    )
    res = client.get("/api/users/me", headers={"Authorization": f"Bearer {forged}"})
    assert res.status_code == 401


def test_존재하지_않는_사용자_토큰은_401(client, db):
    token = auth_utils.create_access_token({"sub": "99999", "name": "유령", "role": "admin"})
    res = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def _sign_with(key, user, expires_in_days=365):
    return jose_jwt.encode(
        {
            "sub": str(user.id),
            "name": user.name,
            "role": user.role,
            "exp": datetime.utcnow() + timedelta(days=expires_in_days),
        },
        key,
        algorithm=auth_utils.ALGORITHM,
    )


def test_레거시_키로_서명한_토큰도_수용(client, make_user):
    """
    SECRET_KEY 교체 시 만료 1년의 기존 토큰이 무효화되어 전 직원이 강제
    로그아웃되는 것을 막는 전환기 폴백. 이 동작이 무중단 배포의 핵심이다.
    """
    user = make_user()
    legacy_token = _sign_with(auth_utils.LEGACY_SECRET_KEY, user)

    res = client.get("/api/users/me", headers={"Authorization": f"Bearer {legacy_token}"})
    assert res.status_code == 200
    assert res.json()["name"] == user.name


def test_새로_발급되는_토큰은_현재_키로만_서명(client, db, mock_sso):
    mock_sso(sub="sso-uuid-9", email="new@bit.kr", name="신규발급")
    token = _sso_login(client).json()["access_token"]

    # 현재 키로는 검증되고
    jose_jwt.decode(token, auth_utils.SECRET_KEY, algorithms=[auth_utils.ALGORITHM])
    # 레거시 키로는 검증되지 않는다
    with pytest.raises(JWTError):
        jose_jwt.decode(token, auth_utils.LEGACY_SECRET_KEY, algorithms=[auth_utils.ALGORITHM])


def test_만료된_레거시_토큰은_거부(client, make_user):
    user = make_user()
    expired = _sign_with(auth_utils.LEGACY_SECRET_KEY, user, expires_in_days=-1)
    res = client.get("/api/users/me", headers={"Authorization": f"Bearer {expired}"})
    assert res.status_code == 401


def test_레거시_폴백_제거후에는_구토큰_거부(client, make_user, monkeypatch):
    """
    전환기(2~4주) 종료 후 LEGACY_SECRET_KEY를 제거했을 때의 동작을 문서화한다.
    이 시점에만 잔여 구토큰 보유자가 재로그인한다.
    """
    user = make_user()
    legacy_token = _sign_with(auth_utils.LEGACY_SECRET_KEY, user)

    monkeypatch.setattr(auth_utils, "LEGACY_SECRET_KEY", None)

    res = client.get("/api/users/me", headers={"Authorization": f"Bearer {legacy_token}"})
    assert res.status_code == 401


def test_관리자_전용_엔드포인트는_일반사용자_거부(client, make_user, auth_headers):
    user = make_user()
    admin = make_user(role="admin")
    assert client.get("/api/users/", headers=auth_headers(user)).status_code == 400
    assert client.get("/api/users/", headers=auth_headers(admin)).status_code == 200


def test_자기_권한은_변경할_수_없음(client, make_user, auth_headers):
    admin = make_user(role="admin")
    res = client.put(
        f"/api/users/{admin.id}/role", headers=auth_headers(admin), json={"role": "user"}
    )
    assert res.status_code == 400


def test_타인_권한_변경(client, db, make_user, auth_headers):
    admin = make_user(role="admin")
    target = make_user()
    res = client.put(
        f"/api/users/{target.id}/role", headers=auth_headers(admin), json={"role": "admin"}
    )
    assert res.status_code == 200
    db.refresh(target)
    assert target.role == "admin"
