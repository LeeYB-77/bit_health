# 별장 예약 이력·통계 엔드포인트(조회 집계 + xlsx 내보내기)를 고정하는 테스트
import io
from datetime import date

import openpyxl

from app import models
from villa_helpers import seed as _seed


def _admin(make_user):
    return make_user(role="admin", email="admin@bit.kr")


def _seed_at(db, user, villa, y, m, d, nights, status="confirmed", booking_type="regular", participant_count=4):
    start = date(y, m, d)
    end = date(y, m, d + nights)
    row = _seed(db, user, villa, start, end, status=status, participant_count=participant_count)
    row.booking_type = booking_type
    db.commit()
    db.refresh(row)
    return row


def _history(client, auth_headers, user, **params):
    return client.get("/api/villa/admin/history", headers=auth_headers(user), params=params)


# --- 집계 ---

def test_이력_요약_집계(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    u = lambda: make_user(email=None)
    _seed_at(db, u(), villa, 2030, 3, 10, 2, status="confirmed")   # 2박
    _seed_at(db, u(), villa, 2030, 5, 10, 3, status="confirmed")   # 3박
    _seed_at(db, u(), villa, 2030, 6, 10, 2, status="canceled")
    _seed_at(db, u(), villa, 2030, 7, 10, 2, status="rejected")

    body = _history(client, auth_headers, _admin(make_user), from_month="2030-01", to_month="2030-12").json()
    s = body["summary"]
    assert s["confirmed_count"] == 2
    assert s["total_nights"] == 5
    assert s["cancel_rate"] == 33.3   # 1 / (2+1)
    assert s["avg_participants"] == 4.0
    assert len(body["reservations"]) == 4

    status_counts = {row["label"]: row["count"] for row in body["by_status"]}
    assert status_counts == {"확정": 2, "취소": 1, "미선정": 1}


def test_취소요청_상태도_확정으로_집계(client, db, facilities, make_user, auth_headers):
    """cancel_requested는 승인 전까지 여전히 점유 중인 확정 예약이다."""
    villa = facilities["cheongpyeong"]
    _seed_at(db, make_user(), villa, 2030, 3, 10, 2, status="cancel_requested")

    body = _history(client, auth_headers, _admin(make_user), from_month="2030-01", to_month="2030-12").json()
    assert body["summary"]["confirmed_count"] == 1
    assert {row["label"] for row in body["by_status"]} == {"확정"}


def test_월별_추이는_빈달도_채운다(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    _seed_at(db, make_user(), villa, 2030, 2, 10, 1, status="confirmed")

    body = _history(client, auth_headers, _admin(make_user), from_month="2030-01", to_month="2030-03").json()
    monthly = {m["month"]: m["count"] for m in body["monthly"]}
    assert monthly == {"2030-01": 0, "2030-02": 1, "2030-03": 0}


def test_별장별_집계(client, db, facilities, make_user, auth_headers):
    _seed_at(db, make_user(), facilities["cheongpyeong"], 2030, 3, 10, 2, status="confirmed")
    _seed_at(db, make_user(), facilities["dongbijae"], 2030, 4, 10, 1, status="confirmed")

    body = _history(client, auth_headers, _admin(make_user), from_month="2030-01", to_month="2030-12").json()
    by_fac = {f["facility"]: f for f in body["by_facility"]}
    assert by_fac["청평별장"]["count"] == 1 and by_fac["청평별장"]["nights"] == 2
    assert by_fac["속초별장"]["count"] == 1 and by_fac["속초별장"]["nights"] == 1


def test_신청유형_집계(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    _seed_at(db, make_user(), villa, 2030, 3, 10, 1, status="confirmed", booking_type="regular")
    _seed_at(db, make_user(), villa, 2030, 4, 10, 1, status="confirmed", booking_type="open")

    body = _history(client, auth_headers, _admin(make_user), from_month="2030-01", to_month="2030-12").json()
    bt = {b["label"]: b["count"] for b in body["by_booking_type"]}
    assert bt == {"정규예약": 1, "선착순": 1}


# --- 필터 ---

def test_별장_필터(client, db, facilities, make_user, auth_headers):
    _seed_at(db, make_user(), facilities["cheongpyeong"], 2030, 3, 10, 1, status="confirmed")
    _seed_at(db, make_user(), facilities["dongbijae"], 2030, 4, 10, 1, status="confirmed")

    body = _history(
        client, auth_headers, _admin(make_user),
        from_month="2030-01", to_month="2030-12", facility_id=facilities["dongbijae"].id,
    ).json()
    assert len(body["reservations"]) == 1
    assert body["reservations"][0]["facility_name"] == "속초별장"


def test_상태_필터(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    _seed_at(db, make_user(), villa, 2030, 3, 10, 1, status="confirmed")
    _seed_at(db, make_user(), villa, 2030, 4, 10, 1, status="canceled")

    body = _history(
        client, auth_headers, _admin(make_user),
        from_month="2030-01", to_month="2030-12", status="canceled",
    ).json()
    assert len(body["reservations"]) == 1
    assert body["reservations"][0]["status"] == "canceled"


def test_기간_필터(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    _seed_at(db, make_user(), villa, 2030, 3, 10, 1, status="confirmed")
    _seed_at(db, make_user(), villa, 2030, 9, 10, 1, status="confirmed")

    body = _history(client, auth_headers, _admin(make_user), from_month="2030-01", to_month="2030-06").json()
    assert len(body["reservations"]) == 1
    assert body["reservations"][0]["start_date"] == "2030-03-10"


# --- 권한 ---

def test_이력은_관리자_전용(client, db, facilities, make_user, auth_headers):
    assert _history(client, auth_headers, make_user(), from_month="2030-01", to_month="2030-12").status_code == 400


def test_위임담당자도_이력_조회(client, db, facilities, make_user, auth_headers):
    manager = make_user(role="user", is_villa_admin=True)
    assert _history(client, auth_headers, manager, from_month="2030-01", to_month="2030-12").status_code == 200


# --- 엑셀 내보내기 ---

def test_엑셀_내보내기(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    _seed_at(db, make_user(name="김이용"), villa, 2030, 3, 10, 2, status="confirmed")
    _seed_at(db, make_user(name="박취소"), villa, 2030, 4, 10, 1, status="canceled")

    res = client.get(
        "/api/villa/admin/history/export",
        headers=auth_headers(_admin(make_user)),
        params={"from_month": "2030-01", "to_month": "2030-12"},
    )
    assert res.status_code == 200
    assert "spreadsheetml" in res.headers["content-type"]
    assert "attachment" in res.headers["content-disposition"]

    wb = openpyxl.load_workbook(io.BytesIO(res.content))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0][0] == "이용자"          # 헤더
    assert len(rows) == 3                   # 헤더 + 2건
    names = {r[0] for r in rows[1:]}
    assert names == {"김이용", "박취소"}


def test_엑셀_내보내기도_관리자_전용(client, db, facilities, make_user, auth_headers):
    res = client.get(
        "/api/villa/admin/history/export",
        headers=auth_headers(make_user()),
        params={"from_month": "2030-01", "to_month": "2030-12"},
    )
    assert res.status_code == 400
