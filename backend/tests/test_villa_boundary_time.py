# 입퇴실 경계일 정규 시간 강제(체크아웃 겹침 시 정규 시간 적용) 동작을 고정하는 테스트
from datetime import date

import pytest

from app import models, villa_notify
from villa_helpers import in_target_month as _in_target_month
from villa_helpers import payload as _payload
from villa_helpers import seed as _seed


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


def _admin(make_user):
    return make_user(role="admin", email="admin@bit.kr")


def _custom_payload(facility_id, start, end, checkin, checkout, participant_count=4):
    p = _payload(facility_id, start, end, participant_count)
    p["checkin_time"] = checkin
    p["checkout_time"] = checkout
    return p


def _open_round(db, start_date):
    """체크인 달의 회차를 통보 완료 상태로 만들어 선착순(즉시 확정)을 연다."""
    db.add(models.VillaBookingRound(
        target_year=start_date.year, target_month=start_date.month,
        apply_start=date(start_date.year, start_date.month, 1),
        apply_end=date(start_date.year, start_date.month, 1),
        notify_date=date(start_date.year, start_date.month, 1),
        status="notified",
    ))
    db.commit()


# --- 기본: 겹치는 예약이 없으면 신청 시간 그대로 ---

def test_인접_예약_없으면_신청시간_그대로(client, db, facilities, make_user, auth_headers, captured):
    villa = facilities["cheongpyeong"]
    start, end = _in_target_month(10, 1), _in_target_month(12, 1)
    _open_round(db, start)

    res = client.post(
        "/api/villa/apply", headers=auth_headers(make_user(email="a@bit.kr")),
        json=_custom_payload(villa.id, start, end, "16:00", "10:00"),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["checkin_time"] == "16:00"
    assert body["checkout_time"] == "10:00"
    assert body["checkin_time_forced"] is False
    assert body["checkout_time_forced"] is False


# --- 체크아웃-체크인 경계 겹침 ---

def test_같은날_퇴실_입실이_겹치면_양쪽_모두_정규시간_강제(client, db, facilities, make_user, auth_headers, captured):
    """선착순도 이제 관리자 확정이 필요하다. 경계 동기화는 확정 시점에 일어난다."""
    villa = facilities["cheongpyeong"]
    d1, d2, d3 = _in_target_month(10, 1), _in_target_month(12, 1), _in_target_month(14, 1)
    _open_round(db, d1)
    headers_admin = auth_headers(_admin(make_user))

    first_user = make_user(email="first@bit.kr")
    res1 = client.post("/api/villa/apply", headers=auth_headers(first_user),
                       json=_custom_payload(villa.id, d1, d2, "16:00", "10:00"))
    assert res1.status_code == 200, res1.text
    assert res1.json()["status"] == "applied"  # 선착순도 즉시 확정이 아니다
    client.post(f"/api/villa/admin/confirm/{res1.json()['id']}", headers=headers_admin)

    second_user = make_user(email="second@bit.kr")
    res2 = client.post("/api/villa/apply", headers=auth_headers(second_user),
                       json=_custom_payload(villa.id, d2, d3, "17:00", "09:00"))
    assert res2.status_code == 200, res2.text
    second_id = res2.json()["id"]
    client.post(f"/api/villa/admin/confirm/{second_id}", headers=headers_admin)

    # 두 번째 예약의 체크인이 첫 예약의 체크아웃(d2)과 겹친다 → 체크인 강제
    second = db.query(models.VillaReservation).filter(models.VillaReservation.id == second_id).one()
    assert second.checkin_time_forced is True
    assert second.checkin_time == "14:00"  # villa_settings 기본값
    # 체크아웃 쪽은 뒤에 아무도 없으니 신청 시간(09:00) 유지
    assert second.checkout_time_forced is False
    assert second.checkout_time == "09:00"

    # 첫 예약도 뒤늦게 강제로 전환됐어야 한다
    row1 = db.query(models.VillaReservation).filter(models.VillaReservation.id == res1.json()["id"]).one()
    assert row1.checkout_time_forced is True
    assert row1.checkout_time == "12:00"
    # 체크인 쪽(앞에 아무도 없음)은 그대로 유지
    assert row1.checkin_time_forced is False
    assert row1.checkin_time == "16:00"


def test_겹치지_않으면_강제_없음(client, db, facilities, make_user, auth_headers, captured):
    """8/10~8/12와 8/13~8/15는 하루 비어 있어(8/12 퇴실, 8/13 입실) 겹치지 않는다."""
    villa = facilities["cheongpyeong"]
    d1, d2 = _in_target_month(10, 1), _in_target_month(12, 1)
    d3, d4 = _in_target_month(13, 1), _in_target_month(15, 1)
    _open_round(db, d1)

    res1 = client.post("/api/villa/apply", headers=auth_headers(make_user(email="a@bit.kr")),
                       json=_custom_payload(villa.id, d1, d2, "16:00", "10:00"))
    res2 = client.post("/api/villa/apply", headers=auth_headers(make_user(email="b@bit.kr")),
                       json=_custom_payload(villa.id, d3, d4, "17:00", "09:00"))

    assert res2.json()["checkin_time_forced"] is False
    assert res2.json()["checkin_time"] == "17:00"
    row1 = db.query(models.VillaReservation).filter(models.VillaReservation.id == res1.json()["id"]).one()
    assert row1.checkout_time_forced is False
    assert row1.checkout_time == "10:00"


# --- 관리자 확정(정규예약) 경로 ---

def test_관리자_확정시에도_경계_동기화(client, db, facilities, make_user, auth_headers, captured):
    villa = facilities["cheongpyeong"]
    d1, d2, d3 = _in_target_month(10), _in_target_month(12), _in_target_month(14)

    first = _seed(db, make_user(email="first@bit.kr"), villa, d1, d2,
                  status="confirmed", checkin_time="16:00", checkout_time="10:00")

    admin = _admin(make_user)
    second_applicant = make_user(email="second@bit.kr")
    res = client.post("/api/villa/apply", headers=auth_headers(second_applicant),
                      json=_custom_payload(villa.id, d2, d3, "17:00", "09:00"))
    assert res.json()["status"] == "applied"  # 정규예약 기간이라 즉시 확정 아님

    second_id = res.json()["id"]
    client.post(f"/api/villa/admin/confirm/{second_id}", headers=auth_headers(admin))

    db.refresh(first)
    second = db.query(models.VillaReservation).filter(models.VillaReservation.id == second_id).one()

    assert second.checkin_time_forced is True
    assert second.checkin_time == "14:00"
    assert first.checkout_time_forced is True
    assert first.checkout_time == "12:00"


def test_확정시_자신의_강제는_별도_알림_없이_상대에게만(client, db, facilities, make_user, auth_headers, captured):
    """
    확정되는 신청 자신의 강제 여부는 이후 admin/notify가 보낼 확정 메시지에 반영되므로
    이 시점에는 알리지 않는다. 이미 확정돼 있던 이웃에게만 즉시 알린다.
    """
    villa = facilities["cheongpyeong"]
    d1, d2, d3 = _in_target_month(10), _in_target_month(12), _in_target_month(14)

    neighbor = make_user(name="이웃", email="neighbor@bit.kr")
    _seed(db, neighbor, villa, d1, d2, status="confirmed", checkin_time="16:00", checkout_time="10:00")

    admin = _admin(make_user)
    applicant = make_user(name="신청자", email="applicant@bit.kr")
    res = client.post("/api/villa/apply", headers=auth_headers(applicant),
                      json=_custom_payload(villa.id, d2, d3, "17:00", "09:00"))
    reservation_id = res.json()["id"]

    captured["mail"].clear()
    client.post(f"/api/villa/admin/confirm/{reservation_id}", headers=auth_headers(admin))

    recipients = {m["to"] for m in captured["mail"]}
    assert recipients == {"neighbor@bit.kr"}, "이웃에게만 즉시 통보되어야 한다"


def test_알림_문구에_정규시간_안내_포함(client, db, facilities, make_user, auth_headers, captured):
    villa = facilities["cheongpyeong"]
    d1, d2, d3 = _in_target_month(10, 1), _in_target_month(12, 1), _in_target_month(14, 1)
    _open_round(db, d1)
    headers_admin = auth_headers(_admin(make_user))

    make_user_first = make_user(email="first@bit.kr")
    res1 = client.post("/api/villa/apply", headers=auth_headers(make_user_first),
               json=_custom_payload(villa.id, d1, d2, "16:00", "10:00"))
    client.post(f"/api/villa/admin/confirm/{res1.json()['id']}", headers=headers_admin)

    captured["mail"].clear()
    captured["slack"].clear()
    res2 = client.post("/api/villa/apply", headers=auth_headers(make_user(email="second@bit.kr")),
               json=_custom_payload(villa.id, d2, d3, "17:00", "09:00"))
    client.post(f"/api/villa/admin/confirm/{res2.json()['id']}", headers=headers_admin)

    # 두 번째 사용자(본인)는 확정 메시지에 강제 안내가 포함된다
    own_mail = next(m for m in captured["mail"] if m["to"] == "second@bit.kr")
    assert "정규 시간" in own_mail["body"]
    assert "14:00" in own_mail["body"]

    # 첫 번째 사용자(이웃)는 별도 정규화 안내 메일을 받는다
    neighbor_mail = next(m for m in captured["mail"] if m["to"] == "first@bit.kr")
    assert "정규 시간" in neighbor_mail["body"]
    assert "12:00" in neighbor_mail["body"]
    assert "퇴실" in neighbor_mail["subject"]


# --- 취소 승인(release) 경로 ---

def test_취소승인되면_이웃의_강제가_해제된다(client, db, facilities, make_user, auth_headers, captured):
    villa = facilities["cheongpyeong"]
    d1, d2, d3 = _in_target_month(10), _in_target_month(12), _in_target_month(14)
    _open_round(db, d1)
    headers_admin = auth_headers(_admin(make_user))

    first_user = make_user(email="first@bit.kr")
    res1 = client.post("/api/villa/apply", headers=auth_headers(first_user),
                       json=_custom_payload(villa.id, d1, d2, "16:00", "10:00"))
    client.post(f"/api/villa/admin/confirm/{res1.json()['id']}", headers=headers_admin)

    second_user = make_user(email="second@bit.kr")
    res2 = client.post("/api/villa/apply", headers=auth_headers(second_user),
                       json=_custom_payload(villa.id, d2, d3, "17:00", "09:00"))
    client.post(f"/api/villa/admin/confirm/{res2.json()['id']}", headers=headers_admin)

    row1 = db.query(models.VillaReservation).filter(models.VillaReservation.id == res1.json()["id"]).one()
    assert row1.checkout_time_forced is True  # 강제된 상태에서 시작

    # 두 번째 예약을 취소 요청 → 승인
    client.post(f"/api/villa/cancel-request/{res2.json()['id']}", headers=auth_headers(second_user), json={})
    client.post(f"/api/villa/admin/cancel-approve/{res2.json()['id']}", headers=headers_admin)

    db.refresh(row1)
    assert row1.checkout_time_forced is False, "이웃이 사라졌으니 강제가 풀려야 한다"
    assert row1.checkout_time == "10:00", "신청했던 시간으로 복귀해야 한다"


def test_취소승인_해제는_알림을_보내지_않는다(client, db, facilities, make_user, auth_headers, captured):
    """요청 범위: 강제가 걸릴 때만 알린다. 해제될 때는 알리지 않는다."""
    villa = facilities["cheongpyeong"]
    d1, d2, d3 = _in_target_month(10), _in_target_month(12), _in_target_month(14)
    _open_round(db, d1)
    headers_admin = auth_headers(_admin(make_user))

    first_user = make_user(email="first@bit.kr")
    res1 = client.post("/api/villa/apply", headers=auth_headers(first_user),
                       json=_custom_payload(villa.id, d1, d2, "16:00", "10:00"))
    client.post(f"/api/villa/admin/confirm/{res1.json()['id']}", headers=headers_admin)

    second_user = make_user(email="second@bit.kr")
    res2 = client.post("/api/villa/apply", headers=auth_headers(second_user),
                       json=_custom_payload(villa.id, d2, d3, "17:00", "09:00"))
    client.post(f"/api/villa/admin/confirm/{res2.json()['id']}", headers=headers_admin)

    client.post(f"/api/villa/cancel-request/{res2.json()['id']}", headers=auth_headers(second_user), json={})
    captured["mail"].clear()
    client.post(f"/api/villa/admin/cancel-approve/{res2.json()['id']}", headers=headers_admin)

    # 취소 승인 통보(notify_cancel_approved)는 second_user에게 가지만
    # first_user에게는 "정규화 해제" 알림이 없어야 한다
    recipients = {m["to"] for m in captured["mail"]}
    assert "first@bit.kr" not in recipients


def test_다른_이웃이_남아있으면_강제_유지(client, db, facilities, make_user, auth_headers, captured):
    """A-B-C 체인에서 B가 취소돼도 A-C는 서로 인접하지 않으므로 각자 상태를 그대로 재평가한다."""
    villa = facilities["cheongpyeong"]
    d1, d2, d3, d4 = (_in_target_month(10), _in_target_month(12),
                      _in_target_month(14), _in_target_month(16))
    admin = _admin(make_user)

    a = _seed(db, make_user(email="a@bit.kr"), villa, d1, d2, status="confirmed",
              checkin_time="16:00", checkout_time="10:00")
    b = _seed(db, make_user(email="b@bit.kr"), villa, d2, d3, status="confirmed",
              checkin_time="16:00", checkout_time="10:00")
    c = _seed(db, make_user(email="c@bit.kr"), villa, d3, d4, status="confirmed",
              checkin_time="16:00", checkout_time="10:00")

    from app.routers import villa as villa_router
    villa_router.sync_boundary_times(db, a)
    villa_router.sync_boundary_times(db, b)
    villa_router.sync_boundary_times(db, c)
    db.commit()
    db.refresh(a); db.refresh(b); db.refresh(c)
    assert a.checkout_time_forced is True
    assert b.checkin_time_forced is True and b.checkout_time_forced is True
    assert c.checkin_time_forced is True

    # B를 취소 승인
    b.status = "cancel_requested"
    db.commit()
    client.post(f"/api/villa/admin/cancel-approve/{b.id}", headers=auth_headers(admin))

    db.refresh(a); db.refresh(c)
    assert a.checkout_time_forced is False, "B가 사라져 A의 퇴실 경계엔 더 이상 이웃이 없다"
    assert c.checkin_time_forced is False, "B가 사라져 C의 입실 경계엔 더 이상 이웃이 없다"


# --- 관리자 신청 목록에도 강제 여부 노출 ---

def test_관리자_신청목록에_강제여부_포함(client, db, facilities, make_user, auth_headers, captured):
    villa = facilities["cheongpyeong"]
    d1, d2, d3 = _in_target_month(10, 1), _in_target_month(12, 1), _in_target_month(14, 1)
    _open_round(db, d1)
    headers_admin = auth_headers(_admin(make_user))

    res1 = client.post("/api/villa/apply", headers=auth_headers(make_user(email="a@bit.kr")),
               json=_custom_payload(villa.id, d1, d2, "16:00", "10:00"))
    client.post(f"/api/villa/admin/confirm/{res1.json()['id']}", headers=headers_admin)
    res2 = client.post("/api/villa/apply", headers=auth_headers(make_user(email="b@bit.kr")),
               json=_custom_payload(villa.id, d2, d3, "17:00", "09:00"))
    client.post(f"/api/villa/admin/confirm/{res2.json()['id']}", headers=headers_admin)

    ny, nm = d1.year, d1.month
    body = client.get(f"/api/villa/admin/applications?year={ny}&month={nm}",
                      headers=headers_admin).json()
    forced_flags = {c["checkin_time_forced"] for c in body["confirmed"]} | \
                    {c["checkout_time_forced"] for c in body["confirmed"]}
    assert True in forced_flags  # 최소 한쪽은 강제되어 있어야 한다


def test_내신청_목록에_강제여부_포함(client, db, facilities, make_user, auth_headers, captured):
    villa = facilities["cheongpyeong"]
    d1, d2, d3 = _in_target_month(10, 1), _in_target_month(12, 1), _in_target_month(14, 1)
    _open_round(db, d1)
    headers_admin = auth_headers(_admin(make_user))

    first_user = make_user(email="first@bit.kr")
    res1 = client.post("/api/villa/apply", headers=auth_headers(first_user),
               json=_custom_payload(villa.id, d1, d2, "16:00", "10:00"))
    client.post(f"/api/villa/admin/confirm/{res1.json()['id']}", headers=headers_admin)

    res2 = client.post("/api/villa/apply", headers=auth_headers(make_user(email="second@bit.kr")),
               json=_custom_payload(villa.id, d2, d3, "17:00", "09:00"))
    client.post(f"/api/villa/admin/confirm/{res2.json()['id']}", headers=headers_admin)

    my = client.get("/api/villa/my", headers=auth_headers(first_user)).json()
    assert my[0]["checkout_time_forced"] is True
    assert my[0]["checkout_time"] == "12:00"
