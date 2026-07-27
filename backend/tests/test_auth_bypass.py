# 레거시 로그인(/api/auth/login)의 생년월일 NULL 매칭 취약점을 고정하는 테스트
#
# 현재 동작:
#   schemas.LoginRequest.birth_date가 Optional=None이고,
#   crud.get_user_by_name_and_birth의 `birth_date == None`이 SQL `IS NULL`로 컴파일된다.
#   SSO 사용자는 birth_date가 NULL이므로 이름만으로 토큰이 발급된다.
#
# 이 파일은 Phase 1에서 401 기대로 뒤집는다. 그 diff가 곧 수정의 증거다.


def _login(client, payload):
    return client.post("/api/auth/login", json=payload)


def test_생년월일_없이_SSO관리자_계정_로그인이_현재_성공한다(client, make_user):
    """
    취약점 고정 테스트. Phase 1 적용 후 401을 기대하도록 수정해야 한다.
    """
    make_user(name="이영배", role="admin", sub="sso-uuid-admin", email="lyb77@bit.kr")

    res = _login(client, {"name": "이영배"})

    assert res.status_code == 200, "현재는 우회가 가능하다 (Phase 1에서 401로 바뀐다)"
    assert res.json()["role"] == "admin"


def test_생년월일_없이_SSO일반사용자_계정_로그인이_현재_성공한다(client, make_user):
    make_user(name="김직원", sub="sso-uuid-1", email="user@bit.kr")

    res = _login(client, {"name": "김직원"})

    assert res.status_code == 200, "현재는 우회가 가능하다 (Phase 1에서 401로 바뀐다)"


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
