# 레거시 로그인(/api/auth/login)의 생년월일 NULL 매칭 취약점이 차단되었음을 보장하는 테스트
#
# 과거 동작(취약):
#   schemas.LoginRequest.birth_date가 Optional=None이고,
#   crud.get_user_by_name_and_birth의 `birth_date == None`이 SQL `IS NULL`로 컴파일되어
#   생년월일이 없는 SSO 사용자가 이름만으로 매칭되었다. 관리자 토큰이 발급될 수 있었다.
#
# 조치(Phase 1):
#   1. crud에서 `birth_date IS NOT NULL` 조건을 추가해 SSO 계정이 이 경로로 매칭되지 않게 함
#   2. LoginRequest.birth_date를 필수로 변경해 스키마 단계에서 차단


def _login(client, payload):
    return client.post("/api/auth/login", json=payload)


def test_생년월일_없이_SSO관리자_계정_로그인_차단(client, make_user):
    make_user(name="이영배", role="admin", sub="sso-uuid-admin", email="lyb77@bit.kr")

    res = _login(client, {"name": "이영배"})

    # 스키마 단계에서 필수 필드 누락으로 거부된다
    assert res.status_code == 422
    assert "access_token" not in res.text


def test_생년월일_null_명시해도_차단(client, make_user):
    make_user(name="이영배", role="admin", sub="sso-uuid-admin", email="lyb77@bit.kr")
    assert _login(client, {"name": "이영배", "birth_date": None}).status_code == 422


def test_빈_생년월일로도_SSO계정에_매칭되지_않음(client, make_user):
    """스키마를 통과하더라도 crud의 IS NOT NULL 조건이 2차로 막는다."""
    make_user(name="김직원", sub="sso-uuid-1", email="user@bit.kr")
    assert _login(client, {"name": "김직원", "birth_date": ""}).status_code == 401


def test_SSO사용자는_레거시_로그인_경로로_인증되지_않음(client, make_user):
    """어떤 생년월일 값을 넣어도 birth_date가 NULL인 계정은 매칭되지 않는다."""
    make_user(name="김직원", sub="sso-uuid-1", email="user@bit.kr")
    for candidate in ["000000", "900101", "null", "None"]:
        assert _login(client, {"name": "김직원", "birth_date": candidate}).status_code == 401


def test_레거시_사용자는_이름과_생년월일로_로그인(client, make_user):
    """Phase 1 이후에도 유지되어야 하는 정상 경로. dev 스크립트가 이 경로를 쓴다."""
    make_user(name="admin", role="admin", birth_date="000000")

    res = _login(client, {"name": "admin", "birth_date": "000000"})
    assert res.status_code == 200
    assert res.json()["role"] == "admin"
    assert res.json()["user_name"] == "admin"


def test_생년월일이_틀리면_401(client, make_user):
    make_user(name="admin", role="admin", birth_date="000000")
    assert _login(client, {"name": "admin", "birth_date": "999999"}).status_code == 401


def test_없는_이름은_401(client):
    assert _login(client, {"name": "존재하지않음", "birth_date": "000000"}).status_code == 401


def test_동명이인_레거시사용자와_SSO사용자_구분(client, make_user):
    """같은 이름의 레거시 계정과 SSO 계정이 공존해도 레거시만 매칭된다."""
    make_user(name="이영배", role="admin", sub="sso-uuid-admin", email="lyb77@bit.kr")
    legacy = make_user(name="이영배", role="user", birth_date="800101")

    res = _login(client, {"name": "이영배", "birth_date": "800101"})
    assert res.status_code == 200
    assert res.json()["role"] == "user", "SSO 관리자 계정이 아니라 레거시 계정이 매칭되어야 한다"


def test_사용자_생성시_생년월일_누락은_400(client, make_user, auth_headers):
    """
    crud에 IS NOT NULL을 추가하면서 함께 정리한 경로.
    이전에는 birth_date=None일 때 len(None)으로 500이 발생했다.
    """
    admin = make_user(role="admin")
    res = client.post("/api/users/", headers=auth_headers(admin), json={"name": "신규직원"})
    assert res.status_code == 400
    assert "6 digits" in res.json()["detail"]


def test_사용자_생성_정상경로(client, db, make_user, auth_headers):
    admin = make_user(role="admin")
    res = client.post(
        "/api/users/",
        headers=auth_headers(admin),
        json={"name": "신규직원", "birth_date": "950505", "department": "영업팀"},
    )
    assert res.status_code == 201
    assert res.json()["name"] == "신규직원"

    # 같은 이름+생년월일 재등록은 거부
    res = client.post(
        "/api/users/",
        headers=auth_headers(admin),
        json={"name": "신규직원", "birth_date": "950505"},
    )
    assert res.status_code == 400
    assert "already registered" in res.json()["detail"]
