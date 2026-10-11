# 별장 슬랙·메일 링크의 매직 링크(서명 토큰으로 로그인 없이 접근) 동작을 고정하는 테스트
from app import auth
from villa_helpers import in_target_month as _in_target_month
from villa_helpers import seed as _seed


def _confirmed(db, facilities, make_user, villa_key="cheongpyeong"):
    owner = make_user(email="owner@bit.kr")
    villa = facilities[villa_key]
    r = _seed(db, owner, villa, _in_target_month(10), _in_target_month(12), status="confirmed")
    return owner, r


def _token(reservation_id, days=120):
    return auth.create_villa_link_token(reservation_id, expire_days=days)


# --- 토큰 헬퍼 ---

def test_토큰_생성_검증_왕복():
    tok = _token(42)
    assert auth.verify_villa_link_token(tok) == 42


def test_만료된_토큰은_None():
    assert auth.verify_villa_link_token(_token(42, days=-1)) is None


def test_엉터리_토큰은_None():
    assert auth.verify_villa_link_token("garbage") is None


# --- 링크 토큰으로 조회 (로그인 없이) ---

def test_링크토큰으로_이용안내_조회(client, db, facilities, make_user):
    _, r = _confirmed(db, facilities, make_user)
    res = client.get(f"/api/villa/{r.id}/guide", params={"t": _token(r.id)})
    assert res.status_code == 200
    assert res.json()["reservation"]["id"] == r.id


def test_링크토큰으로_퇴실체크_조회(client, db, facilities, make_user):
    _, r = _confirmed(db, facilities, make_user)
    res = client.get(f"/api/villa/{r.id}/checkout", params={"t": _token(r.id)})
    assert res.status_code == 200


def test_링크토큰으로_추가입력_조회(client, db, facilities, make_user):
    _, r = _confirmed(db, facilities, make_user)
    res = client.get(f"/api/villa/{r.id}/extra", params={"t": _token(r.id)})
    assert res.status_code == 200


def test_링크토큰으로_퇴실체크_제출(client, db, facilities, make_user):
    _, r = _confirmed(db, facilities, make_user)
    # 청평별장 체크리스트 길이에 맞춘다
    guide = client.get(f"/api/villa/{r.id}/checkout", params={"t": _token(r.id)}).json()
    checked = [True] * len(guide["checklist"])
    res = client.post(
        f"/api/villa/{r.id}/checkout",
        params={"t": _token(r.id)},
        json={"checked": checked, "notes": "링크로 제출"},
    )
    assert res.status_code == 200
    db.refresh(r)
    assert r.checkout_checklist_submitted_at is not None


def test_링크토큰으로_추가입력_저장(client, db, facilities, make_user):
    _, r = _confirmed(db, facilities, make_user)
    res = client.post(
        f"/api/villa/{r.id}/extra",
        params={"t": _token(r.id)},
        json={"vehicle_count": 1, "vehicle_numbers": "12가3456",
              "adult_count": 2, "child_count": 0, "contact_phone": "010-1234-5678"},
    )
    assert res.status_code == 200
    db.refresh(r)
    assert r.contact_phone == "010-1234-5678"


# --- 범위 제한 ---

def test_다른_예약의_토큰은_거부(client, db, facilities, make_user):
    _, r1 = _confirmed(db, facilities, make_user)
    _, r2 = _confirmed(db, facilities, make_user)
    # r2의 토큰으로 r1에 접근 시도
    res = client.get(f"/api/villa/{r1.id}/checkout", params={"t": _token(r2.id)})
    assert res.status_code == 401


def test_토큰도_로그인도_없으면_401(client, db, facilities, make_user):
    _, r = _confirmed(db, facilities, make_user)
    assert client.get(f"/api/villa/{r.id}/checkout").status_code == 401


def test_만료토큰이어도_로그인했으면_통과(client, db, facilities, make_user, auth_headers):
    owner, r = _confirmed(db, facilities, make_user)
    # 만료된 t가 URL에 남아 있어도, 로그인한 본인이면 폴백해 정상 처리한다
    res = client.get(
        f"/api/villa/{r.id}/checkout",
        params={"t": _token(r.id, days=-1)},
        headers=auth_headers(owner),
    )
    assert res.status_code == 200


# --- 기존 사용자 인증 회귀 ---

def test_로그인_사용자_조회_유지(client, db, facilities, make_user, auth_headers):
    owner, r = _confirmed(db, facilities, make_user)
    assert client.get(f"/api/villa/{r.id}/checkout", headers=auth_headers(owner)).status_code == 200


def test_남의_예약은_로그인해도_거부(client, db, facilities, make_user, auth_headers):
    _, r = _confirmed(db, facilities, make_user)
    other = make_user(email="other@bit.kr")
    assert client.get(f"/api/villa/{r.id}/checkout", headers=auth_headers(other)).status_code == 403
