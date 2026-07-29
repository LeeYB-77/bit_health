# 이용안내(체크인 전날)·퇴실 체크사항(체크아웃 당일) 페이지와 알림을 고정하는 테스트
import json
from datetime import date, datetime, timedelta

import pytest

from app import models, villa_notify, villa_scheduler
from villa_helpers import in_target_month as _in_target_month
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


# --- 이용안내 페이지 ---

def test_이용안내_본인만_조회(client, db, facilities, make_user, auth_headers):
    owner = make_user(email="owner@bit.kr")
    other = make_user(email="other@bit.kr")
    villa = facilities["cheongpyeong"]
    r = _seed(db, owner, villa, _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.get(f"/api/villa/{r.id}/guide", headers=auth_headers(owner))
    assert res.status_code == 200
    body = res.json()
    assert body["access"][0]["label"] == "1층 공동현관"
    assert body["access"][0]["steps"][2] == {"code": "1234"}

    res2 = client.get(f"/api/villa/{r.id}/guide", headers=auth_headers(other))
    assert res2.status_code == 403


def test_이용안내_동비재는_12층현관문에_아이콘_포함(client, db, facilities, make_user, auth_headers):
    owner = make_user(email="owner@bit.kr")
    villa = facilities["dongbijae"]
    r = _seed(db, owner, villa, _in_target_month(10), _in_target_month(12), status="confirmed")

    body = client.get(f"/api/villa/{r.id}/guide", headers=auth_headers(owner)).json()
    twelfth_floor = next(a for a in body["access"] if a["label"] == "12층 현관문")
    assert twelfth_floor["steps"] == [{"icon": "bell"}, {"code": "1983*"}]


# --- 퇴실 체크사항 조회/제출 ---

def test_퇴실체크사항_조회(client, db, facilities, make_user, auth_headers):
    owner = make_user(email="owner@bit.kr")
    villa = facilities["cheongpyeong"]
    r = _seed(db, owner, villa, _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.get(f"/api/villa/{r.id}/checkout", headers=auth_headers(owner))
    assert res.status_code == 200
    body = res.json()
    assert len(body["checklist"]) == 9
    assert body["submitted"] is False


def test_퇴실체크사항_제출_길이불일치는_400(client, db, facilities, make_user, auth_headers):
    owner = make_user(email="owner@bit.kr")
    villa = facilities["cheongpyeong"]
    r = _seed(db, owner, villa, _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.post(f"/api/villa/{r.id}/checkout", headers=auth_headers(owner),
                      json={"checked": [True, False], "notes": None})
    assert res.status_code == 400


def test_퇴실체크사항_제출하면_저장되고_관리자에게_슬랙_알림(client, db, facilities, make_user, auth_headers, captured):
    _admin(make_user)
    owner = make_user(name="이용자", email="owner@bit.kr")
    villa = facilities["cheongpyeong"]
    r = _seed(db, owner, villa, _in_target_month(10), _in_target_month(12), status="confirmed")

    checked = [True] * 8 + [False]
    res = client.post(f"/api/villa/{r.id}/checkout", headers=auth_headers(owner),
                      json={"checked": checked, "notes": "거실 전등 하나 고장났습니다."})
    assert res.status_code == 200

    db.refresh(r)
    assert json.loads(r.checkout_checklist_checked) == checked
    assert r.checkout_checklist_notes == "거실 전등 하나 고장났습니다."
    assert r.checkout_checklist_submitted_at is not None

    admin_mail = [m for m in captured["mail"] if m["to"] == "admin@bit.kr"]
    assert len(admin_mail) == 1
    assert "이용자" in admin_mail[0]["body"]
    assert "거실 전등 하나 고장났습니다." in admin_mail[0]["body"]
    assert "❌" in captured["slack"][0]["message"]  # 마지막 항목 미완료 표시


def test_퇴실체크사항_제출도_본인만(client, db, facilities, make_user, auth_headers):
    owner = make_user(email="owner@bit.kr")
    other = make_user(email="other@bit.kr")
    villa = facilities["cheongpyeong"]
    r = _seed(db, owner, villa, _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.post(f"/api/villa/{r.id}/checkout", headers=auth_headers(other),
                      json={"checked": [True] * 9})
    assert res.status_code == 403


# --- 스케줄러: 이용안내(전날)·퇴실체크 알림(당일 7시) ---

def test_체크인_전날_이용안내_발송(db, facilities, make_user, captured):
    owner = make_user(email="owner@bit.kr")
    villa = facilities["cheongpyeong"]
    tomorrow = datetime.now().date() + timedelta(days=1)
    r = _seed(db, owner, villa, tomorrow, tomorrow + timedelta(days=2), status="confirmed")

    sent = villa_scheduler.send_checkin_guides(db, datetime.now().date())
    db.commit()
    assert sent == 1
    db.refresh(r)
    assert r.checkin_guide_sent is True
    assert len(captured["mail"]) == 1
    assert "이용안내" in captured["mail"][0]["subject"]

    # 다시 실행해도 중복 발송하지 않는다
    sent2 = villa_scheduler.send_checkin_guides(db, datetime.now().date())
    db.commit()
    assert sent2 == 0
    assert len(captured["mail"]) == 1


def test_체크인_당일이나_모레는_이용안내_대상_아님(db, facilities, make_user, captured):
    owner = make_user(email="owner@bit.kr")
    villa = facilities["cheongpyeong"]
    today = datetime.now().date()
    _seed(db, owner, villa, today, today + timedelta(days=2), status="confirmed")
    _seed(db, owner, villa, today + timedelta(days=2), today + timedelta(days=4), status="confirmed")

    sent = villa_scheduler.send_checkin_guides(db, today)
    assert sent == 0


def test_퇴실일_오전7시에만_체크사항_슬랙_발송(db, facilities, make_user, captured):
    owner = make_user(email="owner@bit.kr")
    villa = facilities["cheongpyeong"]
    today = datetime.now().date()
    r = _seed(db, owner, villa, today - timedelta(days=2), today, status="confirmed")

    # 7시가 아니면 보내지 않는다
    sent_wrong_hour = villa_scheduler.send_checkout_reminders(db, today, hour=9)
    assert sent_wrong_hour == 0
    assert captured["slack"] == []

    sent = villa_scheduler.send_checkout_reminders(db, today, hour=7)
    db.commit()
    assert sent == 1
    db.refresh(r)
    assert r.checkout_reminder_sent is True
    assert len(captured["slack"]) == 1
    assert "퇴실" in captured["slack"][0]["message"]
    # 메일함이 아니라 현장 알림이므로 슬랙만 간다
    assert captured["mail"] == []

    # 같은 날 다시 7시에 실행해도 중복 발송하지 않는다
    sent2 = villa_scheduler.send_checkout_reminders(db, today, hour=7)
    db.commit()
    assert sent2 == 0
    assert len(captured["slack"]) == 1


# --- 확정 통보의 이용료 안내 ---

def test_확정통보에_이용료_안내_포함(db, facilities, make_user, captured):
    owner = make_user(email="owner@bit.kr")
    villa = facilities["cheongpyeong"]
    r = _seed(db, owner, villa, date(2026, 9, 10), date(2026, 9, 13), status="confirmed")  # 3박

    villa_notify.notify_confirmed(db, r)

    assert len(captured["mail"]) == 1
    body = captured["mail"][0]["body"]
    assert "110,000" in body  # 5+3+3만원
    assert "592-027426-01-020" in body
    assert "3일 이내" in body


@pytest.mark.parametrize("nights,expected", [(1, 50000), (2, 80000), (3, 110000), (4, 140000)])
def test_이용료_계산식(nights, expected):
    assert villa_notify.usage_fee(nights) == expected
