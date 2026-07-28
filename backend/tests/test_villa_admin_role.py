# 별장 위임 관리자(is_villa_admin) 지정, 권한 게이트, 신청 접수 알림을 고정하는 테스트
from app import models, villa_notify
from villa_helpers import in_target_month as _in_target_month
from villa_helpers import payload as _payload

import pytest


@pytest.fixture
def captured(monkeypatch):
    box = {"slack": [], "mail": []}
    monkeypatch.setattr(
        villa_notify.slack_utils, "get_slack_user_id_by_email",
        lambda email: f"U-{email}" if email else None,
    )
    monkeypatch.setattr(
        villa_notify.slack_utils, "send_slack_dm",
        lambda uid, msg: box["slack"].append({"to": uid, "message": msg}),
    )
    monkeypatch.setattr(
        villa_notify.email_utils, "send_mail",
        lambda db, to, subject, body: (box["mail"].append(
            {"to": to, "subject": subject, "body": body}) or True),
    )
    return box


def _sysadmin(make_user):
    return make_user(role="admin", email="sysadmin@bit.kr")


def _villa_manager(make_user):
    """일반 사용자이지만 별장만 위임 관리하는 담당자."""
    return make_user(role="user", is_villa_admin=True, email="villamgr@bit.kr")


# --- 로그인 응답에 플래그 노출 ---

def test_레거시_로그인_응답에_is_villa_admin_포함(client, make_user):
    make_user(name="담당자", birth_date="880101", is_villa_admin=True)
    res = client.post("/api/auth/login", json={"name": "담당자", "birth_date": "880101"})
    assert res.status_code == 200
    assert res.json()["is_villa_admin"] is True


def test_일반_사용자는_is_villa_admin_False(client, make_user):
    make_user(name="평사원", birth_date="880102")
    res = client.post("/api/auth/login", json={"name": "평사원", "birth_date": "880102"})
    assert res.json()["is_villa_admin"] is False


# --- 권한 게이트: 별장 관리 API ---

def test_별장_위임_담당자는_전체_관리자가_아니어도_신청목록_접근(client, facilities, make_user, auth_headers):
    manager = _villa_manager(make_user)
    res = client.get("/api/villa/admin/applications", headers=auth_headers(manager))
    assert res.status_code == 200


def test_일반_사용자는_여전히_거부(client, facilities, make_user, auth_headers):
    plain = make_user(role="user", is_villa_admin=False)
    res = client.get("/api/villa/admin/applications", headers=auth_headers(plain))
    assert res.status_code == 400


def test_전체_관리자는_기존대로_접근(client, facilities, make_user, auth_headers):
    admin = _sysadmin(make_user)
    assert client.get("/api/villa/admin/applications", headers=auth_headers(admin)).status_code == 200
    assert client.get("/api/villa/admin/rounds", headers=auth_headers(admin)).status_code == 200


def test_별장_위임_담당자는_다른_관리_영역은_여전히_차단(client, make_user, auth_headers):
    """golf/users 같은 다른 관리자 전용 API는 role='admin'만 통과해야 한다."""
    manager = _villa_manager(make_user)
    headers = auth_headers(manager)
    assert client.get("/api/users/", headers=headers).status_code == 400
    assert client.get("/api/admin/dashboard/stats", headers=headers).status_code == 403


def test_별장_위임_담당자도_확정_처리_가능(client, db, facilities, make_user, auth_headers):
    manager = _villa_manager(make_user)
    applicant = make_user()
    villa = facilities["cheongpyeong"]
    start, end = _in_target_month(10), _in_target_month(12)

    res = client.post("/api/villa/apply", headers=auth_headers(applicant),
                      json=_payload(villa.id, start, end))
    reservation_id = res.json()["id"]

    res = client.post(f"/api/villa/admin/confirm/{reservation_id}", headers=auth_headers(manager))
    assert res.status_code == 200

    row = db.query(models.VillaReservation).filter(models.VillaReservation.id == reservation_id).one()
    assert row.status == "confirmed"
    assert row.confirmed_by == manager.id


# --- 위임 담당자 지정 엔드포인트 ---

def test_전체_관리자만_담당자_지정_가능(client, make_user, auth_headers):
    admin = _sysadmin(make_user)
    target = make_user(role="user")

    res = client.put(f"/api/users/{target.id}/villa-admin", headers=auth_headers(admin),
                     json={"is_villa_admin": True})
    assert res.status_code == 200
    assert res.json()["is_villa_admin"] is True


def test_일반_사용자는_담당자_지정_불가(client, make_user, auth_headers):
    plain = make_user(role="user")
    target = make_user(role="user")
    res = client.put(f"/api/users/{target.id}/villa-admin", headers=auth_headers(plain),
                     json={"is_villa_admin": True})
    assert res.status_code == 400


def test_담당자_지정_해제(client, db, make_user, auth_headers):
    admin = _sysadmin(make_user)
    target = make_user(role="user", is_villa_admin=True)

    res = client.put(f"/api/users/{target.id}/villa-admin", headers=auth_headers(admin),
                     json={"is_villa_admin": False})
    assert res.status_code == 200
    db.refresh(target)
    assert target.is_villa_admin is False


def test_자기_자신도_지정_가능(client, make_user, auth_headers):
    """role 변경과 달리 자기잠금 위험이 없으므로 제한하지 않는다."""
    admin = _sysadmin(make_user)
    res = client.put(f"/api/users/{admin.id}/villa-admin", headers=auth_headers(admin),
                     json={"is_villa_admin": True})
    assert res.status_code == 200


def test_없는_사용자_지정은_404(client, make_user, auth_headers):
    admin = _sysadmin(make_user)
    res = client.put("/api/users/99999/villa-admin", headers=auth_headers(admin),
                     json={"is_villa_admin": True})
    assert res.status_code == 404


# --- 신청 접수 시 관리자 알림 ---

def test_정규신청시_관리자에게_즉시_알림(client, facilities, make_user, auth_headers, captured):
    _sysadmin(make_user)
    applicant = make_user(name="김직원", department="개발팀", email="kim@bit.kr")
    start, end = _in_target_month(10), _in_target_month(12)

    res = client.post("/api/villa/apply", headers=auth_headers(applicant),
                      json=_payload(facilities["cheongpyeong"].id, start, end))
    assert res.status_code == 200

    assert len(captured["mail"]) == 1
    assert captured["mail"][0]["to"] == "sysadmin@bit.kr"
    assert "김직원" in captured["mail"][0]["body"]
    assert "새 예약 신청" in captured["mail"][0]["subject"]


def test_선착순_확정시에도_관리자에게_알림(client, db, facilities, make_user, auth_headers, captured):
    _sysadmin(make_user)
    villa = facilities["cheongpyeong"]
    start, end = _in_target_month(10, 1), _in_target_month(12, 1)
    db.add(models.VillaBookingRound(
        target_year=start.year, target_month=start.month,
        apply_start=start, apply_end=start, notify_date=start, status="notified",
    ))
    db.commit()

    applicant = make_user(email="kim@bit.kr")
    res = client.post("/api/villa/apply", headers=auth_headers(applicant),
                      json=_payload(villa.id, start, end))
    assert res.status_code == 200
    assert res.json()["status"] == "confirmed"

    admin_mail = [m for m in captured["mail"] if m["to"] == "sysadmin@bit.kr"]
    assert len(admin_mail) == 1
    assert "선착순" in admin_mail[0]["subject"]


def test_별장_위임_담당자도_신청알림을_받는다(client, facilities, make_user, auth_headers, captured):
    """role='admin'이 아니어도 is_villa_admin이면 신청 알림 대상에 포함된다."""
    manager = _villa_manager(make_user)
    applicant = make_user(email="kim@bit.kr")
    start, end = _in_target_month(10), _in_target_month(12)

    client.post("/api/villa/apply", headers=auth_headers(applicant),
               json=_payload(facilities["cheongpyeong"].id, start, end))

    recipients = {m["to"] for m in captured["mail"]}
    assert "villamgr@bit.kr" in recipients


def test_위임_담당자만_있고_전체관리자는_이메일없으면_담당자에게만(client, db, make_user, facilities, auth_headers, captured):
    make_user(role="admin", email=None)  # 이메일 없는 전체 관리자 — 알림 불가 대상
    manager = _villa_manager(make_user)
    applicant = make_user(email="kim@bit.kr")
    start, end = _in_target_month(10), _in_target_month(12)

    client.post("/api/villa/apply", headers=auth_headers(applicant),
               json=_payload(facilities["cheongpyeong"].id, start, end))

    recipients = {m["to"] for m in captured["mail"]}
    assert recipients == {"villamgr@bit.kr"}


def test_취소요청_알림도_위임_담당자에게_간다(client, db, facilities, make_user, auth_headers, captured):
    manager = _villa_manager(make_user)
    applicant = make_user(email="kim@bit.kr")
    villa = facilities["cheongpyeong"]
    start, end = _in_target_month(10), _in_target_month(12)

    row = models.VillaReservation(
        user_id=applicant.id, facility_id=villa.id, start_date=start, end_date=end,
        checkin_time="14:00", checkout_time="12:00",
        requested_checkin_time="14:00", requested_checkout_time="12:00",
        participant_count=2, status="confirmed", booking_type="open",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    captured["mail"].clear()
    res = client.post(f"/api/villa/cancel-request/{row.id}", headers=auth_headers(applicant), json={})
    assert res.status_code == 200

    # 취소 요청 알림은 slack_utils.notify_villa_cancel_request로 직접 발송되므로 mail이 아닌 slack 큐를 본다
    slack_targets = [s["to"] for s in captured["slack"]]
    assert "U-villamgr@bit.kr" in slack_targets
