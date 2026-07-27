# 비트별장 확정 통보와 추가입력 페이지 동작을 고정하는 테스트
from datetime import datetime

import pytest

from app import models, villa_notify
from app.routers import villa as villa_router
from villa_helpers import in_target_month as _in_target_month
from villa_helpers import payload as _payload
from villa_helpers import seed as _seed
from villa_helpers import target_month as _target_month


@pytest.fixture
def captured(monkeypatch):
    """Slack DM과 메일 발송을 가로채 실제 전송 없이 내용만 검사한다."""
    box = {"slack": [], "mail": []}

    monkeypatch.setattr(
        villa_notify.slack_utils, "get_slack_user_id_by_email",
        lambda email: f"U-{email}" if email else None,
    )
    monkeypatch.setattr(
        villa_notify.slack_utils, "send_slack_dm",
        lambda user_id, message: box["slack"].append({"to": user_id, "message": message}),
    )
    monkeypatch.setattr(
        villa_notify.email_utils, "send_mail",
        lambda db, to, subject, body: (box["mail"].append(
            {"to": to, "subject": subject, "body": body}) or True),
    )
    return box


def _admin(make_user):
    return make_user(role="admin", email="admin@bit.kr")


def _confirmed(db, facilities, user, start_day=10, end_day=12):
    row = _seed(db, user, facilities["cheongpyeong"],
                _in_target_month(start_day), _in_target_month(end_day), status="confirmed")
    return row


# --- 통보 문구 ---

def test_확정_통보에_추가입력_링크가_포함(db, facilities, make_user, captured):
    user = make_user(name="김직원", email="kim@bit.kr")
    row = _confirmed(db, facilities, user)

    assert villa_notify.notify_confirmed(db, row) is True

    slack = captured["slack"][0]
    mail = captured["mail"][0]
    link = villa_notify.extra_info_url(row.id)

    assert slack["to"] == "U-kim@bit.kr"
    assert link in slack["message"]
    assert "청평별장" in slack["message"]
    assert "2박" in slack["message"]

    assert mail["to"] == "kim@bit.kr"
    assert link in mail["body"]
    assert "확정" in mail["subject"]


def test_링크는_절대주소(db, facilities, make_user, captured, monkeypatch):
    monkeypatch.setattr(villa_notify, "PUBLIC_BASE_URL", "https://book.bit.kr/")
    row = _confirmed(db, facilities, make_user(email="kim@bit.kr"))
    # 끝의 슬래시가 중복되지 않아야 한다
    assert villa_notify.extra_info_url(row.id) == f"https://book.bit.kr/villa/extra/{row.id}"


def test_미선정_통보(db, facilities, make_user, captured):
    user = make_user(name="박사원", email="park@bit.kr")
    row = _seed(db, user, facilities["cheongpyeong"],
                _in_target_month(10), _in_target_month(12), status="rejected")

    villa_notify.notify_rejected(db, row)

    assert "선착순" in captured["slack"][0]["message"]
    # 미선정 통보에는 추가입력 링크가 없어야 한다
    assert "/villa/extra/" not in captured["slack"][0]["message"]
    assert "/villa/extra/" not in captured["mail"][0]["body"]


def test_이메일_없으면_통보_건너뜀(db, facilities, make_user, captured):
    row = _confirmed(db, facilities, make_user(email=None))
    assert villa_notify.notify_confirmed(db, row) is False
    assert captured["slack"] == []
    assert captured["mail"] == []


def test_slack_실패해도_메일은_발송(db, facilities, make_user, captured, monkeypatch):
    monkeypatch.setattr(
        villa_notify.slack_utils, "get_slack_user_id_by_email",
        lambda email: (_ for _ in ()).throw(RuntimeError("slack down")),
    )
    row = _confirmed(db, facilities, make_user(email="kim@bit.kr"))

    assert villa_notify.notify_confirmed(db, row) is True
    assert captured["slack"] == []
    assert len(captured["mail"]) == 1


def test_메일_실패해도_slack은_발송(db, facilities, make_user, captured, monkeypatch):
    monkeypatch.setattr(villa_notify.email_utils, "send_mail", lambda *a, **kw: False)
    row = _confirmed(db, facilities, make_user(email="kim@bit.kr"))

    assert villa_notify.notify_confirmed(db, row) is True
    assert len(captured["slack"]) == 1


# --- 일괄 통보 ---

def _round_id(db):
    return db.query(models.VillaBookingRound).first().id


def test_일괄_통보(client, db, facilities, make_user, auth_headers, captured):
    admin = _admin(make_user)
    villa = facilities["cheongpyeong"]

    # 신청 2건을 만들어 회차를 생성한다
    winner = make_user(name="선정", email="win@bit.kr")
    loser = make_user(name="탈락", email="lose@bit.kr")
    for user in (winner, loser):
        client.post("/api/villa/apply", headers=auth_headers(user),
                    json=_payload(villa.id, _in_target_month(10), _in_target_month(12)))

    rows = db.query(models.VillaReservation).order_by(models.VillaReservation.id).all()
    client.post(f"/api/villa/admin/confirm/{rows[0].id}", headers=auth_headers(admin))

    res = client.post(f"/api/villa/admin/notify/{_round_id(db)}", headers=auth_headers(admin))
    assert res.status_code == 200
    body = res.json()
    assert body["confirmed"] == 1
    assert body["rejected"] == 1

    recipients = {m["to"] for m in captured["mail"]}
    assert recipients == {"win@bit.kr", "lose@bit.kr"}

    # 회차 상태와 중복 방지 플래그
    db.expire_all()
    assert db.query(models.VillaBookingRound).first().status == "notified"
    assert all(r.notified_confirmed for r in db.query(models.VillaReservation).all())


def test_통보_중복_발송_방지(client, db, facilities, make_user, auth_headers, captured):
    admin = _admin(make_user)
    user = make_user(email="kim@bit.kr")
    client.post("/api/villa/apply", headers=auth_headers(user),
                json=_payload(facilities["cheongpyeong"].id, _in_target_month(10), _in_target_month(12)))
    row = db.query(models.VillaReservation).first()
    client.post(f"/api/villa/admin/confirm/{row.id}", headers=auth_headers(admin))

    rid = _round_id(db)
    client.post(f"/api/villa/admin/notify/{rid}", headers=auth_headers(admin))
    sent_once = len(captured["mail"])

    res = client.post(f"/api/villa/admin/notify/{rid}", headers=auth_headers(admin))
    assert res.status_code == 200
    assert res.json()["confirmed"] == 0
    assert len(captured["mail"]) == sent_once, "이미 통보한 건은 다시 보내지 않는다"


def test_미확정_경합이_남으면_통보_보류(client, db, facilities, make_user, auth_headers, captured):
    admin = _admin(make_user)
    villa = facilities["cheongpyeong"]
    for name in ("A", "B"):
        client.post("/api/villa/apply", headers=auth_headers(make_user(name=name, email=f"{name}@bit.kr")),
                    json=_payload(villa.id, _in_target_month(10), _in_target_month(12)))

    res = client.post(f"/api/villa/admin/notify/{_round_id(db)}", headers=auth_headers(admin))
    assert res.status_code == 400
    assert "확정되지 않은 신청이 2건" in res.json()["detail"]
    assert captured["mail"] == [], "보류 시에는 아무것도 발송하지 않는다"


def test_통보는_관리자_전용(client, db, facilities, make_user, auth_headers):
    assert client.post("/api/villa/admin/notify/1", headers=auth_headers(make_user())).status_code == 400


def test_없는_회차_통보는_404(client, facilities, make_user, auth_headers):
    assert client.post("/api/villa/admin/notify/9999", headers=auth_headers(_admin(make_user))).status_code == 404


# --- 취소 승인/반려 통보 ---

def test_취소_승인시_사용자에게_통보(client, db, facilities, make_user, auth_headers, captured):
    user = make_user(name="요청자", email="req@bit.kr")
    row = _seed(db, user, facilities["cheongpyeong"],
                _in_target_month(10), _in_target_month(12), status="cancel_requested")

    client.post(f"/api/villa/admin/cancel-approve/{row.id}", headers=auth_headers(_admin(make_user)))

    assert captured["mail"][0]["to"] == "req@bit.kr"
    assert "승인" in captured["slack"][0]["message"]


def test_취소_반려시_사용자에게_통보(client, db, facilities, make_user, auth_headers, captured):
    user = make_user(name="요청자", email="req@bit.kr")
    row = _seed(db, user, facilities["cheongpyeong"],
                _in_target_month(10), _in_target_month(12), status="cancel_requested")

    client.post(f"/api/villa/admin/cancel-reject/{row.id}", headers=auth_headers(_admin(make_user)))

    assert "반려" in captured["slack"][0]["message"]
    assert "유지" in captured["mail"][0]["body"]


# --- 추가 입력사항 ---

EXTRA = {"vehicle_count": 2, "vehicle_numbers": "12가3456, 34나5678", "adult_count": 4, "child_count": 2}


def test_추가입력_저장과_조회(client, db, facilities, make_user, auth_headers):
    user = make_user()
    row = _confirmed(db, facilities, user, 10, 12)
    row.participant_count = 6
    db.commit()

    res = client.post(f"/api/villa/{row.id}/extra", headers=auth_headers(user), json=EXTRA)
    assert res.status_code == 200
    body = res.json()
    assert body["vehicle_count"] == 2
    assert body["adult_count"] == 4
    assert body["child_count"] == 2
    assert body["submitted"] is True
    assert body["warning"] is None, "합계가 신청 인원과 같으면 경고가 없다"

    got = client.get(f"/api/villa/{row.id}/extra", headers=auth_headers(user)).json()
    assert got["vehicle_numbers"] == "12가3456, 34나5678"
    assert got["submitted"] is True


def test_인원_불일치는_경고만_하고_저장은_허용(client, db, facilities, make_user, auth_headers):
    user = make_user()
    row = _confirmed(db, facilities, user)
    row.participant_count = 6
    db.commit()

    res = client.post(f"/api/villa/{row.id}/extra", headers=auth_headers(user),
                      json={**EXTRA, "adult_count": 3, "child_count": 1})
    assert res.status_code == 200
    body = res.json()
    assert body["warning"] is not None
    assert "4명" in body["warning"] and "6명" in body["warning"]
    # 경고가 있어도 값은 저장된다
    db.refresh(row)
    assert row.adult_count == 3
    assert row.extra_info_updated_at is not None


def test_타인_예약_추가입력은_403(client, db, facilities, make_user, auth_headers):
    row = _confirmed(db, facilities, make_user())
    stranger = make_user()
    assert client.get(f"/api/villa/{row.id}/extra", headers=auth_headers(stranger)).status_code == 403
    assert client.post(f"/api/villa/{row.id}/extra", headers=auth_headers(stranger), json=EXTRA).status_code == 403


def test_관리자도_타인_추가입력은_403(client, db, facilities, make_user, auth_headers):
    """차량번호는 개인정보라 관리자라도 이 경로로는 열지 않는다."""
    row = _confirmed(db, facilities, make_user())
    assert client.get(f"/api/villa/{row.id}/extra", headers=auth_headers(_admin(make_user))).status_code == 403


@pytest.mark.parametrize("status", ["applied", "rejected", "canceled", "cancel_requested"])
def test_확정_상태가_아니면_추가입력_거부(client, db, facilities, make_user, auth_headers, status):
    user = make_user()
    row = _seed(db, user, facilities["cheongpyeong"],
                _in_target_month(10), _in_target_month(12), status=status)
    res = client.post(f"/api/villa/{row.id}/extra", headers=auth_headers(user), json=EXTRA)
    assert res.status_code == 400
    assert "확정된 예약만" in res.json()["detail"]


def test_음수_입력은_400(client, db, facilities, make_user, auth_headers):
    user = make_user()
    row = _confirmed(db, facilities, user)
    res = client.post(f"/api/villa/{row.id}/extra", headers=auth_headers(user),
                      json={**EXTRA, "adult_count": -1})
    assert res.status_code == 400


def test_없는_예약_추가입력은_404(client, facilities, make_user, auth_headers):
    assert client.get("/api/villa/99999/extra", headers=auth_headers(make_user())).status_code == 404


def test_추가입력_전에는_needs_extra_info가_True(client, db, facilities, make_user, auth_headers):
    user = make_user()
    row = _confirmed(db, facilities, user)

    before = client.get("/api/villa/my", headers=auth_headers(user)).json()
    assert before[0]["needs_extra_info"] is True

    client.post(f"/api/villa/{row.id}/extra", headers=auth_headers(user), json=EXTRA)

    after = client.get("/api/villa/my", headers=auth_headers(user)).json()
    assert after[0]["needs_extra_info"] is False


def test_차량번호_공백만_입력하면_None(client, db, facilities, make_user, auth_headers):
    user = make_user()
    row = _confirmed(db, facilities, user)
    client.post(f"/api/villa/{row.id}/extra", headers=auth_headers(user),
                json={**EXTRA, "vehicle_count": 0, "vehicle_numbers": "   "})
    db.refresh(row)
    assert row.vehicle_numbers is None
