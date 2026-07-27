# SSO 로그인 처리와 JWT 발급/검증의 현재 동작을 고정하는 테스트
import pytest
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


def test_sso_관리자_판정은_현재_이름_하드코딩(client, db, mock_sso):
    """
    현재 동작 고정: routers/auth.py에서 name == "이영배"이면 admin이 된다.
    Phase 4에서 환경변수 기반으로 교체하면 이 테스트를 함께 수정한다.
    """
    mock_sso(sub="sso-uuid-admin", email="lyb77@bit.kr", name="이영배")
    res = _sso_login(client)
    assert res.status_code == 200
    assert res.json()["role"] == "admin"


def test_sso_이름이_다르면_일반사용자(client, mock_sso):
    mock_sso(sub="sso-uuid-2", email="other@bit.kr", name="박사원")
    assert _sso_login(client).json()["role"] == "user"


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
