# 선착순 예약과 회차 자동 전이(마감·리마인더·통보) 동작을 고정하는 테스트
from datetime import date, datetime, timedelta

import pytest

from app import models, villa_notify, villa_scheduler
from app.routers import villa as villa_router
from villa_helpers import in_target_month as _in_target_month
from villa_helpers import payload as _payload
from villa_helpers import seed as _seed
from villa_helpers import target_month as _target_month


@pytest.fixture
def captured(monkeypatch):
    box = {"slack": [], "mail": [], "admin_alerts": []}
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


def _make_round(db, year, month, *, apply_end, notify_date, status="open", **kw):
    row = models.VillaBookingRound(
        target_year=year, target_month=month,
        apply_start=date(year, month, 1),
        apply_end=apply_end, notify_date=notify_date,
        status=status, **kw,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _admin(make_user):
    return make_user(role="admin", email="admin@bit.kr")


@pytest.fixture
def isolate_current_round(db):
    """
    스케줄러는 실행할 때마다 현재 대상월 회차를 자동 생성한다.
    오늘이 월말에 가까우면 그 회차가 마감 임박 리마인더를 발생시켜,
    알림 건수를 세는 테스트가 '오늘이 며칠이냐'에 따라 흔들린다.
    (실제로 7/27에는 통과하다가 7/28에 깨졌다.)
    미리 플래그를 세운 상태로 만들어 두어 검사 대상에서 제외한다.
    """
    year, month = _target_month()
    apply_start, apply_end, notify_date = villa_router.apply_window_for_target(year, month)
    db.add(models.VillaBookingRound(
        target_year=year, target_month=month,
        apply_start=apply_start, apply_end=apply_end, notify_date=notify_date,
        status="open", reminder_sent=True, notify_warning_sent=True,
    ))
    db.commit()


# --- 선착순 예약 ---

def _notified_round_for(db, start_date):
    """체크인 달의 회차를 '통보 완료' 상태로 만들어 선착순을 연다."""
    return _make_round(
        db, start_date.year, start_date.month,
        apply_end=date(start_date.year, start_date.month, 1) - timedelta(days=1),
        notify_date=date(start_date.year, start_date.month, 1) - timedelta(days=1),
        status="notified",
    )


def test_통보완료된_달은_선착순으로_즉시_확정(client, db, facilities, make_user, auth_headers, captured):
    # 대상월 다음 달을 통보 완료 상태로 만든다
    start = _in_target_month(10, 1)
    end = _in_target_month(12, 1)
    _notified_round_for(db, start)

    user = make_user(email="kim@bit.kr")
    res = client.post("/api/villa/apply", headers=auth_headers(user),
                      json=_payload(facilities["cheongpyeong"].id, start, end))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "confirmed"
    assert body["booking_type"] == "open"

    row = db.query(models.VillaReservation).filter(models.VillaReservation.id == body["id"]).one()
    assert row.confirmed_at is not None
    # 즉시 통보했으므로 일괄 통보 대상에서 빠져야 한다
    assert row.notified_confirmed is True


def test_선착순_확정시_추가입력_링크_통보(client, db, facilities, make_user, auth_headers, captured):
    start, end = _in_target_month(10, 1), _in_target_month(12, 1)
    _notified_round_for(db, start)

    user = make_user(email="kim@bit.kr")
    res = client.post("/api/villa/apply", headers=auth_headers(user),
                      json=_payload(facilities["cheongpyeong"].id, start, end))

    link = villa_notify.extra_info_url(res.json()["id"])
    assert link in captured["slack"][0]["message"]
    assert captured["mail"][0]["to"] == "kim@bit.kr"


def test_선착순도_확정된_기간과_겹치면_409(client, db, facilities, make_user, auth_headers, captured):
    start, end = _in_target_month(10, 1), _in_target_month(12, 1)
    _notified_round_for(db, start)
    _seed(db, make_user(), facilities["cheongpyeong"], start, end, status="confirmed")

    res = client.post("/api/villa/apply", headers=auth_headers(make_user()),
                      json=_payload(facilities["cheongpyeong"].id, start, end))
    assert res.status_code == 409


def test_선착순_먼저_신청한_사람이_차지(client, db, facilities, make_user, auth_headers, captured):
    start, end = _in_target_month(10, 1), _in_target_month(12, 1)
    _notified_round_for(db, start)
    villa = facilities["cheongpyeong"]

    first = client.post("/api/villa/apply", headers=auth_headers(make_user(email="a@bit.kr")),
                        json=_payload(villa.id, start, end))
    second = client.post("/api/villa/apply", headers=auth_headers(make_user(email="b@bit.kr")),
                         json=_payload(villa.id, start, end))

    assert first.status_code == 200
    assert second.status_code == 409


def test_마감됐지만_통보_전인_달은_신청_불가(client, db, facilities, make_user, auth_headers):
    """결과가 나오기 전에는 선착순을 열지 않는다."""
    start, end = _in_target_month(10, 1), _in_target_month(12, 1)
    _make_round(
        db, start.year, start.month,
        apply_end=date(start.year, start.month, 1) - timedelta(days=1),
        notify_date=date(start.year, start.month, 1) - timedelta(days=1),
        status="closed",
    )
    res = client.post("/api/villa/apply", headers=auth_headers(make_user()),
                      json=_payload(facilities["cheongpyeong"].id, start, end))
    assert res.status_code == 400


def test_회차가_없는_미래달은_신청_불가(client, facilities, make_user, auth_headers):
    res = client.post("/api/villa/apply", headers=auth_headers(make_user()),
                      json=_payload(facilities["cheongpyeong"].id,
                                    _in_target_month(10, 2), _in_target_month(12, 2)))
    assert res.status_code == 400


def test_달력이_신청_방식을_알려준다(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    headers = auth_headers(make_user())
    ty, tm = _target_month()

    body = client.get(f"/api/villa/calendar?facility_id={villa.id}&year={ty}&month={tm}",
                      headers=headers).json()
    assert body["booking_mode"] == "regular"

    ny, nm = _target_month(1)
    body = client.get(f"/api/villa/calendar?facility_id={villa.id}&year={ny}&month={nm}",
                      headers=headers).json()
    assert body["booking_mode"] == "closed"

    _notified_round_for(db, date(ny, nm, 1))
    body = client.get(f"/api/villa/calendar?facility_id={villa.id}&year={ny}&month={nm}",
                      headers=headers).json()
    assert body["booking_mode"] == "open"


# --- 회차 자동 전이 ---

def test_현재_대상월_회차를_미리_생성(db):
    assert db.query(models.VillaBookingRound).count() == 0
    villa_scheduler.run(db)

    rounds = db.query(models.VillaBookingRound).all()
    assert len(rounds) == 1
    assert (rounds[0].target_year, rounds[0].target_month) == _target_month()


def test_회차_생성은_멱등(db):
    villa_scheduler.run(db)
    villa_scheduler.run(db)
    villa_scheduler.run(db)
    assert db.query(models.VillaBookingRound).count() == 1


def test_마감일_지난_회차는_closed(db):
    today = datetime.now().date()
    past = _make_round(db, 2020, 3, apply_end=today - timedelta(days=1),
                       notify_date=today + timedelta(days=30))

    villa_scheduler.run(db)
    db.refresh(past)
    assert past.status == "closed"


def test_마감일_당일에는_아직_열려있다(db):
    """마감일까지는 신청을 받는다. 다음 날부터 닫힌다."""
    today = datetime.now().date()
    row = _make_round(db, 2020, 3, apply_end=today, notify_date=today)

    villa_scheduler.run(db)
    db.refresh(row)
    assert row.status == "open"


def test_마감_임박_리마인더는_1회만(db, make_user, captured, isolate_current_round):
    _admin(make_user)
    today = datetime.now().date()
    row = _make_round(db, 2020, 3, apply_end=today + timedelta(days=2),
                      notify_date=today + timedelta(days=2))

    villa_scheduler.run(db)
    db.refresh(row)
    assert row.reminder_sent is True
    first = len(captured["mail"])
    assert first == 1
    assert "마감" in captured["slack"][0]["message"]

    villa_scheduler.run(db)
    assert len(captured["mail"]) == first, "리마인더는 한 번만 보낸다"


def test_마감이_멀면_리마인더_없음(db, make_user, captured, isolate_current_round):
    _admin(make_user)
    today = datetime.now().date()
    row = _make_round(db, 2020, 3, apply_end=today + timedelta(days=10),
                      notify_date=today + timedelta(days=10))

    villa_scheduler.run(db)
    db.refresh(row)
    assert row.reminder_sent is False
    assert captured["mail"] == []


def test_통보일_도달시_자동_통보(db, facilities, make_user, captured, isolate_current_round):
    today = datetime.now().date()
    row = _make_round(db, 2020, 3, apply_end=today - timedelta(days=2),
                      notify_date=today - timedelta(days=1), status="closed")

    winner = make_user(name="선정", email="win@bit.kr")
    loser = make_user(name="탈락", email="lose@bit.kr")
    for user, status in ((winner, "confirmed"), (loser, "rejected")):
        r = _seed(db, user, facilities["cheongpyeong"],
                  _in_target_month(10), _in_target_month(12), status=status)
        r.round_id = row.id
    db.commit()

    summary = villa_scheduler.run(db)
    assert summary["confirmed"] == 1
    assert summary["rejected"] == 1

    db.refresh(row)
    assert row.status == "notified"
    assert {m["to"] for m in captured["mail"]} == {"win@bit.kr", "lose@bit.kr"}


def test_자동_통보는_중복_발송하지_않음(db, facilities, make_user, captured, isolate_current_round):
    today = datetime.now().date()
    row = _make_round(db, 2020, 3, apply_end=today - timedelta(days=2),
                      notify_date=today - timedelta(days=1), status="closed")
    r = _seed(db, make_user(email="win@bit.kr"), facilities["cheongpyeong"],
              _in_target_month(10), _in_target_month(12), status="confirmed")
    r.round_id = row.id
    db.commit()

    villa_scheduler.run(db)
    sent = len(captured["mail"])
    villa_scheduler.run(db)
    assert len(captured["mail"]) == sent


def test_미확정_경합이_남으면_통보_보류하고_관리자_경고(db, facilities, make_user, captured, isolate_current_round):
    _admin(make_user)
    today = datetime.now().date()
    row = _make_round(db, 2020, 3, apply_end=today - timedelta(days=2),
                      notify_date=today - timedelta(days=1), status="closed")

    applicant = make_user(name="대기자", email="wait@bit.kr")
    r = _seed(db, applicant, facilities["cheongpyeong"],
              _in_target_month(10), _in_target_month(12), status="applied")
    r.round_id = row.id
    db.commit()

    summary = villa_scheduler.run(db)
    assert summary["blocked"] == 1
    assert summary["confirmed"] == 0

    db.refresh(row)
    assert row.status == "closed", "임의 선정 없이 보류한다"
    assert row.notify_warning_sent is True

    # 경고는 관리자에게만 가고 신청자에게는 가지 않는다
    assert {m["to"] for m in captured["mail"]} == {"admin@bit.kr"}
    assert "보류" in captured["slack"][0]["message"]


def test_통보_보류_경고도_1회만(db, facilities, make_user, captured, isolate_current_round):
    _admin(make_user)
    today = datetime.now().date()
    row = _make_round(db, 2020, 3, apply_end=today - timedelta(days=2),
                      notify_date=today - timedelta(days=1), status="closed")
    r = _seed(db, make_user(email="wait@bit.kr"), facilities["cheongpyeong"],
              _in_target_month(10), _in_target_month(12), status="applied")
    r.round_id = row.id
    db.commit()

    villa_scheduler.run(db)
    first = len(captured["mail"])
    villa_scheduler.run(db)
    assert len(captured["mail"]) == first


def test_보류후_확정하면_다음_실행에서_통보(db, facilities, make_user, captured, isolate_current_round):
    _admin(make_user)
    today = datetime.now().date()
    row = _make_round(db, 2020, 3, apply_end=today - timedelta(days=2),
                      notify_date=today - timedelta(days=1), status="closed")
    r = _seed(db, make_user(name="신청자", email="wait@bit.kr"), facilities["cheongpyeong"],
              _in_target_month(10), _in_target_month(12), status="applied")
    r.round_id = row.id
    db.commit()

    villa_scheduler.run(db)          # 보류
    r.status = "confirmed"
    db.commit()

    summary = villa_scheduler.run(db)  # 이제 통보
    assert summary["confirmed"] == 1
    db.refresh(row)
    assert row.status == "notified"
    assert "wait@bit.kr" in {m["to"] for m in captured["mail"]}


def test_한_번의_실행으로_open에서_notified까지(db, facilities, make_user, captured, isolate_current_round):
    """
    마감과 통보가 같은 실행 안에서 연달아 일어나야 한다.
    SessionLocal이 autoflush=False라 flush를 빠뜨리면 통보 단계가
    방금 closed로 바꾼 회차를 보지 못하고 한 주기를 더 기다리게 된다.
    """
    today = datetime.now().date()
    row = _make_round(db, 2020, 3, apply_end=today - timedelta(days=2),
                      notify_date=today - timedelta(days=1), status="open")
    r = _seed(db, make_user(name="선정", email="win@bit.kr"), facilities["cheongpyeong"],
              _in_target_month(10), _in_target_month(12), status="confirmed")
    r.round_id = row.id
    db.commit()

    summary = villa_scheduler.run(db)
    assert summary["closed"] == 1
    assert summary["confirmed"] == 1, "같은 실행에서 통보까지 마쳐야 한다"

    db.refresh(row)
    assert row.status == "notified"
    assert "win@bit.kr" in {m["to"] for m in captured["mail"]}


def test_통보일_전에는_통보하지_않음(db, facilities, make_user, captured, isolate_current_round):
    today = datetime.now().date()
    row = _make_round(db, 2020, 3, apply_end=today - timedelta(days=1),
                      notify_date=today + timedelta(days=3), status="closed")
    r = _seed(db, make_user(email="win@bit.kr"), facilities["cheongpyeong"],
              _in_target_month(10), _in_target_month(12), status="confirmed")
    r.round_id = row.id
    db.commit()

    summary = villa_scheduler.run(db)
    assert summary["confirmed"] == 0
    db.refresh(row)
    assert row.status == "closed"
    assert captured["mail"] == []


def test_scheduled_job은_예외를_삼킨다(monkeypatch):
    """스케줄러 실패가 다른 작업으로 번지면 안 된다."""
    monkeypatch.setattr(villa_scheduler, "run", lambda db: (_ for _ in ()).throw(RuntimeError("boom")))
    villa_scheduler.scheduled_job()  # 예외가 밖으로 나오지 않아야 한다
