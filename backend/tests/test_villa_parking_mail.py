# 동비재 주차등록 요청 메일(관리실 주소 설정 → 초안 확인·수정 → 발송)을 고정하는 테스트
import pytest

from app import villa_notify
from villa_helpers import in_target_month as _in_target_month
from villa_helpers import seed as _seed

OFFICE = "office@moritz.kr"


@pytest.fixture
def sent(monkeypatch):
    """실제 SMTP 발송 대신 호출 내용을 담아 둔다. 실패 시나리오는 raises로 갈아끼운다."""
    box = []
    monkeypatch.setattr(
        villa_notify.email_utils, "send_mail_or_raise",
        lambda db, to, subject, body: box.append({"to": to, "subject": subject, "body": body}),
    )
    return box


def _villa_manager(make_user):
    return make_user(role="user", email="villamgr@bit.kr", is_villa_admin=True)


def _set_office_email(client, auth_headers, manager, email=OFFICE):
    return client.post(
        "/api/villa/admin/settings",
        headers=auth_headers(manager),
        json={"parking_office_email": email},
    )


def _confirmed_dongbijae(db, facilities, user):
    return _seed(
        db, user, facilities["dongbijae"],
        _in_target_month(10), _in_target_month(12), status="confirmed",
    )


def _save_extra(client, auth_headers, user, reservation, vehicle_numbers="12가3456"):
    return client.post(
        f"/api/villa/{reservation.id}/extra",
        headers=auth_headers(user),
        json={
            "vehicle_count": 1 if vehicle_numbers else 0,
            "vehicle_numbers": vehicle_numbers,
            "adult_count": 4,
            "child_count": 0,
            "contact_phone": "010-1234-5678",
        },
    )


# --- 관리실 메일 주소 설정 ---

def test_관리실_메일_저장_후_조회(client, db, make_user, auth_headers):
    manager = _villa_manager(make_user)

    res = _set_office_email(client, auth_headers, manager)
    assert res.status_code == 200
    assert res.json()["parking_office_email"] == OFFICE

    got = client.get("/api/villa/admin/settings", headers=auth_headers(manager))
    assert got.status_code == 200
    assert got.json()["parking_office_email"] == OFFICE


def test_관리실_메일_설정전에는_빈값(client, db, make_user, auth_headers):
    manager = _villa_manager(make_user)
    got = client.get("/api/villa/admin/settings", headers=auth_headers(manager))
    assert got.json()["parking_office_email"] == ""


def test_잘못된_메일형식은_400(client, db, make_user, auth_headers):
    manager = _villa_manager(make_user)
    res = _set_office_email(client, auth_headers, manager, "관리실주소")
    assert res.status_code == 400


def test_빈값으로_저장하면_기능_해제(client, db, facilities, make_user, auth_headers):
    manager = _villa_manager(make_user)
    _set_office_email(client, auth_headers, manager)
    assert _set_office_email(client, auth_headers, manager, "").status_code == 200

    guest = make_user(email="guest@bit.kr")
    reservation = _confirmed_dongbijae(db, facilities, guest)
    body = _save_extra(client, auth_headers, guest, reservation).json()
    assert body["parking_mail"] is None


def test_설정을_저장해도_다른_별장설정은_보존(client, db, make_user, auth_headers):
    """villa_settings 한 행에 함께 들어가므로 성수기 규칙 등을 덮어쓰지 않아야 한다."""
    from app.routers import villa as villa_router

    manager = _villa_manager(make_user)
    _set_office_email(client, auth_headers, manager)

    settings = villa_router.get_villa_settings_data(db)
    assert settings["peak_months"] == [7, 8]
    assert settings["default_checkin_time"] == "14:00"


def test_설정_변경은_관리자_전용(client, db, make_user, auth_headers):
    """비트별장 관리 게이트는 다른 admin API와 같이 400으로 막는다."""
    plain = make_user(email="plain@bit.kr")
    assert client.get("/api/villa/admin/settings", headers=auth_headers(plain)).status_code == 400
    assert _set_office_email(client, auth_headers, plain).status_code == 400


# --- 저장 응답의 메일 초안 ---

def test_동비재_저장시_메일_초안_반환(client, db, facilities, make_user, auth_headers):
    manager = _villa_manager(make_user)
    _set_office_email(client, auth_headers, manager)

    guest = make_user(name="김이용", email="guest@bit.kr")
    reservation = _confirmed_dongbijae(db, facilities, guest)

    body = _save_extra(client, auth_headers, guest, reservation).json()
    draft = body["parking_mail"]
    assert draft["to"] == OFFICE
    assert draft["subject"] == "102동1201호 주차등록 부탁드립니다."
    # 이름·연락처·이용기간·차량번호가 모두 본문에 들어간다.
    assert "김이용" in draft["body"]
    assert "010-1234-5678" in draft["body"]
    assert str(_in_target_month(10)) in draft["body"]
    assert "12가3456" in draft["body"]


def test_청평별장은_초안을_만들지_않는다(client, db, facilities, make_user, auth_headers):
    manager = _villa_manager(make_user)
    _set_office_email(client, auth_headers, manager)

    guest = make_user(email="guest@bit.kr")
    reservation = _seed(
        db, guest, facilities["cheongpyeong"],
        _in_target_month(10), _in_target_month(12), status="confirmed",
    )
    body = _save_extra(client, auth_headers, guest, reservation).json()
    assert body["parking_mail"] is None


def test_차량이_없으면_초안을_만들지_않는다(client, db, facilities, make_user, auth_headers):
    manager = _villa_manager(make_user)
    _set_office_email(client, auth_headers, manager)

    guest = make_user(email="guest@bit.kr")
    reservation = _confirmed_dongbijae(db, facilities, guest)
    body = _save_extra(client, auth_headers, guest, reservation, vehicle_numbers=None).json()
    assert body["parking_mail"] is None


def test_저장만으로는_메일이_발송되지_않는다(client, db, facilities, make_user, auth_headers, sent):
    """확인·수정 단계를 거쳐야 하므로 저장 시점에 바로 나가면 안 된다."""
    manager = _villa_manager(make_user)
    _set_office_email(client, auth_headers, manager)

    guest = make_user(email="guest@bit.kr")
    reservation = _confirmed_dongbijae(db, facilities, guest)
    _save_extra(client, auth_headers, guest, reservation)
    assert sent == []


# --- 발송 ---

def test_수정한_내용으로_발송(client, db, facilities, make_user, auth_headers, sent):
    manager = _villa_manager(make_user)
    _set_office_email(client, auth_headers, manager)

    guest = make_user(email="guest@bit.kr")
    reservation = _confirmed_dongbijae(db, facilities, guest)
    _save_extra(client, auth_headers, guest, reservation)

    res = client.post(
        f"/api/villa/{reservation.id}/parking-mail",
        headers=auth_headers(guest),
        json={"subject": "제목 수정함", "body": "본문 수정함"},
    )
    assert res.status_code == 200
    assert sent == [{"to": OFFICE, "subject": "제목 수정함", "body": "본문 수정함"}]


def test_수신자는_설정값만_쓴다(client, db, facilities, make_user, auth_headers, sent):
    """클라이언트가 to를 보내도 무시해야 한다 — 아니면 메일 릴레이가 된다."""
    manager = _villa_manager(make_user)
    _set_office_email(client, auth_headers, manager)

    guest = make_user(email="guest@bit.kr")
    reservation = _confirmed_dongbijae(db, facilities, guest)
    _save_extra(client, auth_headers, guest, reservation)

    client.post(
        f"/api/villa/{reservation.id}/parking-mail",
        headers=auth_headers(guest),
        json={"subject": "제목", "body": "본문", "to": "attacker@evil.com"},
    )
    assert sent[0]["to"] == OFFICE


def test_제목이나_본문이_비면_400(client, db, facilities, make_user, auth_headers, sent):
    manager = _villa_manager(make_user)
    _set_office_email(client, auth_headers, manager)

    guest = make_user(email="guest@bit.kr")
    reservation = _confirmed_dongbijae(db, facilities, guest)

    res = client.post(
        f"/api/villa/{reservation.id}/parking-mail",
        headers=auth_headers(guest),
        json={"subject": "   ", "body": "본문"},
    )
    assert res.status_code == 400
    assert sent == []


def test_청평별장은_발송_거부(client, db, facilities, make_user, auth_headers, sent):
    manager = _villa_manager(make_user)
    _set_office_email(client, auth_headers, manager)

    guest = make_user(email="guest@bit.kr")
    reservation = _seed(
        db, guest, facilities["cheongpyeong"],
        _in_target_month(10), _in_target_month(12), status="confirmed",
    )
    res = client.post(
        f"/api/villa/{reservation.id}/parking-mail",
        headers=auth_headers(guest),
        json={"subject": "제목", "body": "본문"},
    )
    assert res.status_code == 400
    assert sent == []


def test_관리실_주소가_없으면_발송_거부(client, db, facilities, make_user, auth_headers, sent):
    guest = make_user(email="guest@bit.kr")
    reservation = _confirmed_dongbijae(db, facilities, guest)

    res = client.post(
        f"/api/villa/{reservation.id}/parking-mail",
        headers=auth_headers(guest),
        json={"subject": "제목", "body": "본문"},
    )
    assert res.status_code == 400
    assert sent == []


def test_확정이_아니면_발송_거부(client, db, facilities, make_user, auth_headers, sent):
    manager = _villa_manager(make_user)
    _set_office_email(client, auth_headers, manager)

    guest = make_user(email="guest@bit.kr")
    reservation = _seed(
        db, guest, facilities["dongbijae"],
        _in_target_month(10), _in_target_month(12), status="applied",
    )
    res = client.post(
        f"/api/villa/{reservation.id}/parking-mail",
        headers=auth_headers(guest),
        json={"subject": "제목", "body": "본문"},
    )
    assert res.status_code == 400
    assert sent == []


def test_남의_예약은_발송_거부(client, db, facilities, make_user, auth_headers, sent):
    manager = _villa_manager(make_user)
    _set_office_email(client, auth_headers, manager)

    guest = make_user(email="guest@bit.kr")
    other = make_user(email="other@bit.kr")
    reservation = _confirmed_dongbijae(db, facilities, guest)

    res = client.post(
        f"/api/villa/{reservation.id}/parking-mail",
        headers=auth_headers(other),
        json={"subject": "제목", "body": "본문"},
    )
    assert res.status_code == 403
    assert sent == []


def test_발송_실패는_502로_알린다(client, db, facilities, make_user, auth_headers, monkeypatch):
    """조용히 성공한 것처럼 보이면 등록이 된 줄 알고 넘어간다."""
    manager = _villa_manager(make_user)
    _set_office_email(client, auth_headers, manager)

    def boom(db, to, subject, body):
        raise RuntimeError("SMTP 설정이 완료되지 않았습니다.")

    monkeypatch.setattr(villa_notify.email_utils, "send_mail_or_raise", boom)

    guest = make_user(email="guest@bit.kr")
    reservation = _confirmed_dongbijae(db, facilities, guest)

    res = client.post(
        f"/api/villa/{reservation.id}/parking-mail",
        headers=auth_headers(guest),
        json={"subject": "제목", "body": "본문"},
    )
    assert res.status_code == 502
    assert "SMTP" in res.json()["detail"]
