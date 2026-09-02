# 비트별장 관리자 확정·취소 승인 동작을 고정하는 테스트
from datetime import date, datetime, timedelta

import pytest

from app import models
from app.routers import villa as villa_router
from villa_helpers import (
    in_target_month as _in_target_month,
    payload as _payload,
    seed as _seed,
    target_month as _target_month,
)


def _admin(make_user):
    return make_user(role="admin", email="admin@bit.kr")


# --- 신청 목록과 경합 그룹 ---

def test_신청목록은_관리자_전용(client, facilities, make_user, auth_headers):
    assert client.get("/api/villa/admin/applications", headers=auth_headers(make_user())).status_code == 400
    assert client.get("/api/villa/admin/applications", headers=auth_headers(_admin(make_user))).status_code == 200


def test_같은_기간_신청은_한_그룹으로_묶임(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    for name in ("김직원", "박사원", "이과장"):
        _seed(db, make_user(name=name, department="개발팀"), villa, _in_target_month(10), _in_target_month(12))

    body = client.get("/api/villa/admin/applications", headers=auth_headers(_admin(make_user))).json()
    assert body["pending_total"] == 3
    assert body["contested_groups"] == 1
    assert len(body["groups"]) == 1

    group = body["groups"][0]
    assert group["count"] == 3
    assert group["contested"] is True
    assert group["facility_name"] == "청평별장"
    assert {a["user_name"] for a in group["applications"]} == {"김직원", "박사원", "이과장"}


def test_겹치지_않는_신청은_별도_그룹(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    _seed(db, make_user(), villa, _in_target_month(10), _in_target_month(12))
    _seed(db, make_user(), villa, _in_target_month(20), _in_target_month(22))

    body = client.get("/api/villa/admin/applications", headers=auth_headers(_admin(make_user))).json()
    assert len(body["groups"]) == 2
    assert body["contested_groups"] == 0
    assert all(g["contested"] is False for g in body["groups"])


def test_신청현황은_대상월과_다른_달도_모두_보인다(client, db, facilities, make_user, auth_headers):
    """대기 신청은 페이지에 표시 중인 달(year/month 파라미터)과 무관하게 전부 노출돼야 한다."""
    villa = facilities["cheongpyeong"]
    _seed(db, make_user(name="이번달"), villa, _in_target_month(10), _in_target_month(12))
    _seed(db, make_user(name="다음달"), villa, _in_target_month(10, 1), _in_target_month(12, 1))

    body = client.get("/api/villa/admin/applications", headers=auth_headers(_admin(make_user))).json()
    names = {a["user_name"] for g in body["groups"] for a in g["applications"]}
    assert names == {"이번달", "다음달"}
    assert body["pending_total"] == 2


def test_체인_겹침은_연결요소로_묶임(client, db, facilities, make_user, auth_headers):
    """A(10~12) - B(11~13) - C(12~14): A와 C는 안 겹치지만 B를 통해 한 덩어리다."""
    villa = facilities["cheongpyeong"]
    _seed(db, make_user(name="A"), villa, _in_target_month(10), _in_target_month(12))
    _seed(db, make_user(name="B"), villa, _in_target_month(11), _in_target_month(13))
    _seed(db, make_user(name="C"), villa, _in_target_month(12), _in_target_month(14))

    body = client.get("/api/villa/admin/applications", headers=auth_headers(_admin(make_user))).json()
    assert len(body["groups"]) == 1
    assert body["groups"][0]["count"] == 3


def test_다른_별장은_그룹이_분리됨(client, db, facilities, make_user, auth_headers):
    _seed(db, make_user(), facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12))
    _seed(db, make_user(), facilities["dongbijae"], _in_target_month(10), _in_target_month(12))

    body = client.get("/api/villa/admin/applications", headers=auth_headers(_admin(make_user))).json()
    assert len(body["groups"]) == 2
    assert {g["facility_name"] for g in body["groups"]} == {"청평별장", "속초별장"}


def test_통보대기건수는_해당_회차만_센다(client, db, facilities, make_user, auth_headers):
    """
    confirmed 목록이 더 이상 달로 좁혀지지 않으므로, 통보 대상 건수는 반드시
    round_id로 직접 세야 한다. 다른 회차의 확정 건이 섞여 잘못 커지면 안 된다.
    """
    villa = facilities["cheongpyeong"]
    ty, tm = _target_month()
    current_round = villa_router.get_or_create_round(db, ty, tm)

    other_round = models.VillaBookingRound(
        target_year=2020, target_month=3,
        apply_start=date(2020, 1, 1), apply_end=date(2020, 1, 31), notify_date=date(2020, 1, 31),
        status="notified",
    )
    db.add(other_round)
    db.commit()

    # 다른 회차에 속한, 아직 통보 안 된 확정 건 — 이게 섞이면 버그다.
    other = _seed(db, make_user(name="다른회차"), villa, date(2020, 3, 10), date(2020, 3, 12), status="confirmed")
    other.round_id = other_round.id
    other.notified_confirmed = False

    mine = _seed(db, make_user(name="이번회차"), villa, _in_target_month(10), _in_target_month(12), status="confirmed")
    mine.round_id = current_round.id
    mine.notified_confirmed = False
    db.commit()

    body = client.get("/api/villa/admin/applications", headers=auth_headers(_admin(make_user))).json()
    assert body["unnotified_count"] == 1


def test_이용이력_횟수가_함께_제공됨(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    heavy = make_user(name="단골")
    # 최근 1년 내 확정 이력 2건
    today = datetime.now().date()
    for delta in (30, 60):
        _seed(db, heavy, villa, today - timedelta(days=delta), today - timedelta(days=delta - 2), status="confirmed")
    # 1년보다 오래된 건은 집계에서 빠진다
    _seed(db, heavy, villa, today - timedelta(days=500), today - timedelta(days=498), status="confirmed")

    _seed(db, heavy, villa, _in_target_month(10), _in_target_month(12))
    _seed(db, make_user(name="신입"), villa, _in_target_month(10), _in_target_month(12))

    body = client.get("/api/villa/admin/applications", headers=auth_headers(_admin(make_user))).json()
    by_name = {a["user_name"]: a for g in body["groups"] for a in g["applications"]}
    assert by_name["단골"]["usage_count"] == 2
    assert by_name["신입"]["usage_count"] == 0


def test_신청_목록은_신청_순서대로(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    first = _seed(db, make_user(name="먼저"), villa, _in_target_month(10), _in_target_month(12))
    second = _seed(db, make_user(name="나중"), villa, _in_target_month(10), _in_target_month(12))
    first.created_at = datetime.now() - timedelta(days=5)
    second.created_at = datetime.now()
    db.commit()

    body = client.get("/api/villa/admin/applications", headers=auth_headers(_admin(make_user))).json()
    names = [a["user_name"] for a in body["groups"][0]["applications"]]
    assert names == ["먼저", "나중"]


# --- 확정 ---

def test_확정하면_겹치는_나머지가_미선정(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    winner = _seed(db, make_user(name="선정"), villa, _in_target_month(10), _in_target_month(12))
    loser = _seed(db, make_user(name="탈락"), villa, _in_target_month(10), _in_target_month(12))

    res = client.post(f"/api/villa/admin/confirm/{winner.id}", headers=auth_headers(_admin(make_user)))
    assert res.status_code == 200
    assert res.json()["rejected_count"] == 1

    db.refresh(winner)
    db.refresh(loser)
    assert winner.status == "confirmed"
    assert winner.confirmed_at is not None
    assert winner.confirmed_by is not None
    assert loser.status == "rejected"


def test_확정은_직접_겹치는_건만_떨어뜨린다(client, db, facilities, make_user, auth_headers):
    """
    A(10~12) - B(11~13) - C(12~14) 체인에서 A를 확정하면
    A와 겹치는 B만 미선정이고, 겹치지 않는 C는 살아남아야 한다.
    연결 요소 전체를 떨어뜨리면 C가 부당하게 탈락한다.
    """
    villa = facilities["cheongpyeong"]
    a = _seed(db, make_user(name="A"), villa, _in_target_month(10), _in_target_month(12))
    b = _seed(db, make_user(name="B"), villa, _in_target_month(11), _in_target_month(13))
    c = _seed(db, make_user(name="C"), villa, _in_target_month(12), _in_target_month(14))

    res = client.post(f"/api/villa/admin/confirm/{a.id}", headers=auth_headers(_admin(make_user)))
    assert res.status_code == 200
    assert res.json()["rejected_count"] == 1

    db.refresh(a); db.refresh(b); db.refresh(c)
    assert a.status == "confirmed"
    assert b.status == "rejected"
    assert c.status == "applied", "겹치지 않는 신청은 살아남아야 한다"


def test_다른_별장_신청은_영향_없음(client, db, facilities, make_user, auth_headers):
    a = _seed(db, make_user(), facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12))
    other = _seed(db, make_user(), facilities["dongbijae"], _in_target_month(10), _in_target_month(12))

    client.post(f"/api/villa/admin/confirm/{a.id}", headers=auth_headers(_admin(make_user)))
    db.refresh(other)
    assert other.status == "applied"


def test_이미_확정된_기간에는_재확정_거부(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    _seed(db, make_user(), villa, _in_target_month(10), _in_target_month(12), status="confirmed")
    late = _seed(db, make_user(), villa, _in_target_month(11), _in_target_month(13))

    res = client.post(f"/api/villa/admin/confirm/{late.id}", headers=auth_headers(_admin(make_user)))
    assert res.status_code == 409
    db.refresh(late)
    assert late.status == "applied"


@pytest.mark.parametrize("status", ["confirmed", "canceled", "rejected", "cancel_requested"])
def test_applied가_아니면_확정_거부(client, db, facilities, make_user, auth_headers, status):
    row = _seed(db, make_user(), facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status=status)
    res = client.post(f"/api/villa/admin/confirm/{row.id}", headers=auth_headers(_admin(make_user)))
    assert res.status_code == 400


def test_확정은_관리자_전용(client, db, facilities, make_user, auth_headers):
    row = _seed(db, make_user(), facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12))
    assert client.post(f"/api/villa/admin/confirm/{row.id}", headers=auth_headers(make_user())).status_code == 400


def test_없는_신청_확정은_404(client, facilities, make_user, auth_headers):
    assert client.post("/api/villa/admin/confirm/99999", headers=auth_headers(_admin(make_user))).status_code == 404


def test_확정_후_사용자_달력에_이름이_보인다(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    ty, tm = _target_month()
    applicant = make_user(name="확정자", department="개발팀")
    row = _seed(db, applicant, villa, _in_target_month(10), _in_target_month(12))

    client.post(f"/api/villa/admin/confirm/{row.id}", headers=auth_headers(_admin(make_user)))

    viewer = make_user()
    body = client.get(
        f"/api/villa/calendar?facility_id={villa.id}&year={ty}&month={tm}",
        headers=auth_headers(viewer),
    ).json()
    confirmed = [i for i in body["items"] if i["status"] == "confirmed"]
    assert len(confirmed) == 1
    assert confirmed[0]["user_name"] == "확정자"


# --- 취소 승인 / 반려 ---

def test_취소요청_목록(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    user = make_user(name="요청자", department="영업팀")
    row = _seed(db, user, villa, _in_target_month(10), _in_target_month(12), status="cancel_requested")
    row.cancel_requested_at = datetime.now()
    row.cancel_reason = "개인 사정"
    db.commit()

    body = client.get("/api/villa/admin/cancel-requests", headers=auth_headers(_admin(make_user))).json()
    assert len(body) == 1
    assert body[0]["user_name"] == "요청자"
    assert body[0]["cancel_reason"] == "개인 사정"
    assert body[0]["nights"] == 2


def test_취소요청_목록은_대기중인_것만(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    _seed(db, make_user(), villa, _in_target_month(10), _in_target_month(12), status="confirmed")
    _seed(db, make_user(), villa, _in_target_month(20), _in_target_month(22), status="canceled")

    body = client.get("/api/villa/admin/cancel-requests", headers=auth_headers(_admin(make_user))).json()
    assert body == []


def test_취소_승인하면_기간이_다시_열린다(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    row = _seed(db, make_user(), villa, _in_target_month(10), _in_target_month(12), status="cancel_requested")

    res = client.post(f"/api/villa/admin/cancel-approve/{row.id}", headers=auth_headers(_admin(make_user)))
    assert res.status_code == 200
    db.refresh(row)
    assert row.status == "canceled"
    assert row.canceled_at is not None
    assert row.canceled_by is not None

    # 같은 기간에 다시 신청 가능해야 한다
    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(villa.id, _in_target_month(10), _in_target_month(12)),
    )
    assert res.status_code == 200, res.text


def test_취소_반려하면_확정으로_복귀(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    row = _seed(db, make_user(), villa, _in_target_month(10), _in_target_month(12), status="cancel_requested")
    row.cancel_requested_at = datetime.now()
    row.cancel_reason = "변심"
    db.commit()

    res = client.post(f"/api/villa/admin/cancel-reject/{row.id}", headers=auth_headers(_admin(make_user)))
    assert res.status_code == 200

    db.refresh(row)
    assert row.status == "confirmed"
    # 요청 흔적을 남기면 UI에 '취소 요청중'으로 잘못 보인다
    assert row.cancel_requested_at is None
    assert row.cancel_reason is None

    # 기간은 계속 점유된 상태여야 한다
    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(villa.id, _in_target_month(10), _in_target_month(12)),
    )
    assert res.status_code == 409


@pytest.mark.parametrize("endpoint", ["cancel-approve", "cancel-reject"])
@pytest.mark.parametrize("status", ["applied", "confirmed", "canceled"])
def test_취소요청_상태가_아니면_400(client, db, facilities, make_user, auth_headers, endpoint, status):
    row = _seed(db, make_user(), facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status=status)
    res = client.post(f"/api/villa/admin/{endpoint}/{row.id}", headers=auth_headers(_admin(make_user)))
    assert res.status_code == 400


@pytest.mark.parametrize("endpoint", ["cancel-approve", "cancel-reject"])
def test_취소처리는_관리자_전용(client, db, facilities, make_user, auth_headers, endpoint):
    row = _seed(db, make_user(), facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status="cancel_requested")
    assert client.post(f"/api/villa/admin/{endpoint}/{row.id}", headers=auth_headers(make_user())).status_code == 400


# --- 담당자 직접 취소 ---

@pytest.mark.parametrize("status", ["applied", "confirmed", "cancel_requested"])
def test_담당자_직접취소는_활성_예약을_취소한다(client, db, facilities, make_user, auth_headers, status):
    villa = facilities["cheongpyeong"]
    row = _seed(db, make_user(email="guest@bit.kr"), villa, _in_target_month(10), _in_target_month(12), status=status)

    res = client.post(
        f"/api/villa/admin/cancel/{row.id}",
        headers=auth_headers(_admin(make_user)),
        json={"reason": "시설 점검"},
    )
    assert res.status_code == 200, res.text
    db.refresh(row)
    assert row.status == "canceled"
    assert row.canceled_at is not None
    assert row.canceled_by is not None
    assert row.cancel_reason == "시설 점검"


def test_담당자_취소후_기간이_다시_열린다(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    row = _seed(db, make_user(), villa, _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.post(
        f"/api/villa/admin/cancel/{row.id}",
        headers=auth_headers(_admin(make_user)),
        json={"reason": "중복 예약 정리"},
    )
    assert res.status_code == 200

    # 같은 기간에 다시 신청 가능해야 한다
    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(villa.id, _in_target_month(10), _in_target_month(12)),
    )
    assert res.status_code == 200, res.text


def test_담당자_취소는_사유가_필수(client, db, facilities, make_user, auth_headers):
    row = _seed(db, make_user(), facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status="confirmed")
    res = client.post(
        f"/api/villa/admin/cancel/{row.id}",
        headers=auth_headers(_admin(make_user)),
        json={"reason": "   "},
    )
    assert res.status_code == 400
    db.refresh(row)
    assert row.status == "confirmed"  # 취소되지 않았다


@pytest.mark.parametrize("status", ["canceled", "rejected"])
def test_이미_취소된_예약은_다시_취소_불가(client, db, facilities, make_user, auth_headers, status):
    row = _seed(db, make_user(), facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status=status)
    res = client.post(
        f"/api/villa/admin/cancel/{row.id}",
        headers=auth_headers(_admin(make_user)),
        json={"reason": "사유"},
    )
    assert res.status_code == 400


def test_없는_예약_취소는_404(client, db, facilities, make_user, auth_headers):
    res = client.post(
        "/api/villa/admin/cancel/999999",
        headers=auth_headers(_admin(make_user)),
        json={"reason": "사유"},
    )
    assert res.status_code == 404


def test_담당자_취소는_관리자_전용(client, db, facilities, make_user, auth_headers):
    row = _seed(db, make_user(), facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status="confirmed")
    res = client.post(
        f"/api/villa/admin/cancel/{row.id}",
        headers=auth_headers(make_user()),
        json={"reason": "사유"},
    )
    assert res.status_code == 400
    db.refresh(row)
    assert row.status == "confirmed"


def test_별장_위임_담당자도_직접취소_가능(client, db, facilities, make_user, auth_headers):
    manager = make_user(role="user", is_villa_admin=True)
    row = _seed(db, make_user(email="guest@bit.kr"), facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status="confirmed")
    res = client.post(
        f"/api/villa/admin/cancel/{row.id}",
        headers=auth_headers(manager),
        json={"reason": "담당자 처리"},
    )
    assert res.status_code == 200
    db.refresh(row)
    assert row.status == "canceled"
    assert row.canceled_by == manager.id


# --- 회차 관리 ---

def test_회차_목록과_대기건수(client, db, facilities, make_user, auth_headers):
    ty, tm = _target_month()
    # 신청이 들어오면 회차가 생성된다
    client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(facilities["cheongpyeong"].id, _in_target_month(10), _in_target_month(12)),
    )

    body = client.get("/api/villa/admin/rounds", headers=auth_headers(_admin(make_user))).json()
    assert len(body) == 1
    assert (body[0]["target_year"], body[0]["target_month"]) == (ty, tm)
    assert body[0]["pending_count"] == 1
    assert body[0]["status"] == "open"


def test_회차_수동_생성(client, db, facilities, make_user, auth_headers):
    res = client.post(
        "/api/villa/admin/rounds",
        headers=auth_headers(_admin(make_user)),
        json={"target_year": 2027, "target_month": 3},
    )
    assert res.status_code == 200
    body = res.json()
    # 2027년 3월 대상 → 2027년 1월 접수
    assert body["apply_start"] == "2027-01-01"
    assert body["apply_end"] == "2027-01-31"
    assert body["notify_date"] == "2027-01-31"
    assert body["status"] == "open"


def test_회차_조기_마감(client, db, facilities, make_user, auth_headers):
    ty, tm = _target_month()
    headers = auth_headers(_admin(make_user))

    client.post("/api/villa/admin/rounds", headers=headers,
                json={"target_year": ty, "target_month": tm, "status": "closed"})

    # 마감된 회차에는 신규 신청이 막힌다
    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(facilities["cheongpyeong"].id, _in_target_month(10), _in_target_month(12)),
    )
    assert res.status_code == 400
    assert "마감" in res.json()["detail"]


def test_회차_잘못된_입력은_400(client, facilities, make_user, auth_headers):
    headers = auth_headers(_admin(make_user))
    assert client.post("/api/villa/admin/rounds", headers=headers,
                       json={"target_year": 2027, "target_month": 13}).status_code == 400
    assert client.post("/api/villa/admin/rounds", headers=headers,
                       json={"target_year": 2027, "target_month": 3, "status": "bogus"}).status_code == 400


def test_회차_관리는_관리자_전용(client, facilities, make_user, auth_headers):
    headers = auth_headers(make_user())
    assert client.get("/api/villa/admin/rounds", headers=headers).status_code == 400
    assert client.post("/api/villa/admin/rounds", headers=headers,
                       json={"target_year": 2027, "target_month": 3}).status_code == 400


# --- 키 불출/회수 ---

def test_키불출_기록(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    row = _seed(db, make_user(), villa, _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.post(f"/api/villa/admin/key/{row.id}", headers=auth_headers(_admin(make_user)),
                      json={"key_number": "K-07"})
    assert res.status_code == 200

    db.refresh(row)
    assert row.key_number == "K-07"
    assert row.key_issued_at is not None
    assert row.key_returned_at is None


def test_확정_상태가_아니면_키불출_거부(client, db, facilities, make_user, auth_headers):
    row = _seed(db, make_user(), facilities["cheongpyeong"],
                _in_target_month(10), _in_target_month(12), status="applied")
    res = client.post(f"/api/villa/admin/key/{row.id}", headers=auth_headers(_admin(make_user)),
                      json={"key_number": "K-07"})
    assert res.status_code == 400


def test_키번호_공백만_입력하면_400(client, db, facilities, make_user, auth_headers):
    row = _seed(db, make_user(), facilities["cheongpyeong"],
                _in_target_month(10), _in_target_month(12), status="confirmed")
    res = client.post(f"/api/villa/admin/key/{row.id}", headers=auth_headers(_admin(make_user)),
                      json={"key_number": "   "})
    assert res.status_code == 400


def test_키회수_처리(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    row = _seed(db, make_user(), villa, _in_target_month(10), _in_target_month(12), status="confirmed")
    admin_headers = auth_headers(_admin(make_user))
    client.post(f"/api/villa/admin/key/{row.id}", headers=admin_headers, json={"key_number": "K-07"})

    res = client.post(f"/api/villa/admin/key-return/{row.id}", headers=admin_headers)
    assert res.status_code == 200

    db.refresh(row)
    assert row.key_returned_at is not None
    assert row.key_number == "K-07", "회수해도 어떤 키였는지 기록은 남긴다"


def test_불출된_키가_없으면_회수_거부(client, db, facilities, make_user, auth_headers):
    row = _seed(db, make_user(), facilities["cheongpyeong"],
                _in_target_month(10), _in_target_month(12), status="confirmed")
    res = client.post(f"/api/villa/admin/key-return/{row.id}", headers=auth_headers(_admin(make_user)))
    assert res.status_code == 400


def test_이미_회수된_키는_다시_회수_거부(client, db, facilities, make_user, auth_headers):
    row = _seed(db, make_user(), facilities["cheongpyeong"],
                _in_target_month(10), _in_target_month(12), status="confirmed")
    admin_headers = auth_headers(_admin(make_user))
    client.post(f"/api/villa/admin/key/{row.id}", headers=admin_headers, json={"key_number": "K-07"})
    client.post(f"/api/villa/admin/key-return/{row.id}", headers=admin_headers)

    res = client.post(f"/api/villa/admin/key-return/{row.id}", headers=admin_headers)
    assert res.status_code == 400


def test_재불출하면_회수기록_초기화(client, db, facilities, make_user, auth_headers):
    """반납 후 다음 이용자에게 같은 예약 슬롯으로 다시 키를 내주는 경우(재불출)를 지원한다."""
    row = _seed(db, make_user(), facilities["cheongpyeong"],
                _in_target_month(10), _in_target_month(12), status="confirmed")
    admin_headers = auth_headers(_admin(make_user))
    client.post(f"/api/villa/admin/key/{row.id}", headers=admin_headers, json={"key_number": "K-07"})
    client.post(f"/api/villa/admin/key-return/{row.id}", headers=admin_headers)

    res = client.post(f"/api/villa/admin/key/{row.id}", headers=admin_headers, json={"key_number": "K-08"})
    assert res.status_code == 200

    db.refresh(row)
    assert row.key_number == "K-08"
    assert row.key_returned_at is None


def test_키관리는_관리자_전용(client, db, facilities, make_user, auth_headers):
    row = _seed(db, make_user(), facilities["cheongpyeong"],
                _in_target_month(10), _in_target_month(12), status="confirmed")
    headers = auth_headers(make_user())
    assert client.post(f"/api/villa/admin/key/{row.id}", headers=headers,
                       json={"key_number": "K-07"}).status_code == 400
    assert client.post(f"/api/villa/admin/key-return/{row.id}", headers=headers).status_code == 400


def test_없는_예약_키관리는_404(client, facilities, make_user, auth_headers):
    headers = auth_headers(_admin(make_user))
    assert client.post("/api/villa/admin/key/99999", headers=headers,
                       json={"key_number": "K-07"}).status_code == 404
    assert client.post("/api/villa/admin/key-return/99999", headers=headers).status_code == 404


def test_별장_위임_관리자도_키관리_가능(client, db, facilities, make_user, auth_headers):
    manager = make_user(role="user", is_villa_admin=True)
    row = _seed(db, make_user(), facilities["cheongpyeong"],
                _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.post(f"/api/villa/admin/key/{row.id}", headers=auth_headers(manager),
                      json={"key_number": "K-07"})
    assert res.status_code == 200


def test_신청목록_응답에_키정보_포함(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    row = _seed(db, make_user(), villa, _in_target_month(10), _in_target_month(12), status="confirmed")
    admin_headers = auth_headers(_admin(make_user))
    client.post(f"/api/villa/admin/key/{row.id}", headers=admin_headers, json={"key_number": "K-07"})

    body = client.get("/api/villa/admin/applications", headers=admin_headers).json()
    confirmed = next(c for c in body["confirmed"] if c["id"] == row.id)
    assert confirmed["key_number"] == "K-07"
    assert confirmed["key_issued_at"] is not None
    assert confirmed["key_returned_at"] is None
