# 골프 슬롯 생성 규칙(평일/주말/공휴일)과 슬롯 점유 표시의 현재 동작을 고정하는 테스트
import json
from datetime import datetime, timedelta

from app import models

# 요일과 공휴일 여부를 고정하기 위해 실제 날짜를 사용한다.
WEEKDAY = "2027-01-06"  # 수요일, 공휴일 아님
WEEKEND = "2027-01-09"  # 토요일
HOLIDAY = "2027-01-01"  # 금요일이지만 신정(공휴일)


def _get_slots(client, headers, date):
    res = client.get(f"/api/golf/slots?date={date}", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_평일은_기본_2시간_블록_3개(client, facilities, make_user, auth_headers):
    slots = _get_slots(client, auth_headers(make_user()), WEEKDAY)
    assert [(s["time"], s["end_time"]) for s in slots] == [
        ("10:00", "12:00"),
        ("14:00", "16:00"),
        ("19:00", "21:00"),
    ]
    assert all(s["type"] == "weekday" for s in slots)
    assert all(s["available"] for s in slots)


def test_주말은_1시간_단위_9개(client, facilities, make_user, auth_headers):
    slots = _get_slots(client, auth_headers(make_user()), WEEKEND)
    # weekend_start=9, weekend_end=18 → 9시부터 17시 시작까지 9개
    assert len(slots) == 9
    assert slots[0]["time"] == "09:00" and slots[0]["end_time"] == "10:00"
    assert slots[-1]["time"] == "17:00" and slots[-1]["end_time"] == "18:00"
    assert all(s["type"] == "weekend" for s in slots)


def test_공휴일은_평일이어도_주말_규칙_적용(client, facilities, make_user, auth_headers):
    slots = _get_slots(client, auth_headers(make_user()), HOLIDAY)
    assert len(slots) == 9
    assert all(s["type"] == "weekend" for s in slots)


def test_잘못된_날짜형식은_400(client, facilities, make_user, auth_headers):
    res = client.get("/api/golf/slots?date=2027/01/06", headers=auth_headers(make_user()))
    assert res.status_code == 400


def test_예약된_슬롯은_점유상태와_우선순위를_노출(
    client, db, facilities, make_user, auth_headers
):
    owner = make_user()
    start = datetime.fromisoformat(f"{WEEKDAY}T10:00:00")
    db.add(
        models.Reservation(
            user_id=owner.id,
            facility_id=facilities["golf"].id,
            start_time=start,
            end_time=start + timedelta(hours=2),
            participant_count=1,
            status="reserved",
            priority=2,
        )
    )
    db.commit()

    slots = _get_slots(client, auth_headers(make_user()), WEEKDAY)
    taken = slots[0]
    assert taken["available"] is False
    assert taken["taken_by_priority"] == 2
    assert taken["taken_res_id"] is not None
    # 먼 미래 날짜이므로 3시간 제한을 통과한다
    assert taken["can_preempt"] is True
    # 나머지 슬롯은 영향 없음
    assert slots[1]["available"] is True


def test_본인_예약_슬롯은_선점대상이_아님(client, db, facilities, make_user, auth_headers):
    user = make_user()
    start = datetime.fromisoformat(f"{WEEKDAY}T10:00:00")
    db.add(
        models.Reservation(
            user_id=user.id,
            facility_id=facilities["golf"].id,
            start_time=start,
            end_time=start + timedelta(hours=2),
            participant_count=1,
            status="reserved",
            priority=3,
        )
    )
    db.commit()

    slots = _get_slots(client, auth_headers(user), WEEKDAY)
    assert slots[0]["available"] is False
    assert slots[0]["can_preempt"] is False


def test_설정_변경이_슬롯_생성에_반영(client, db, facilities, make_user, auth_headers):
    db.add(
        models.SystemSetting(
            key="golf_settings",
            value=json.dumps(
                {
                    "weekday_slots": [{"start": "08:00", "end": "09:00"}],
                    "weekend_start": 10,
                    "weekend_end": 12,
                }
            ),
        )
    )
    db.commit()

    headers = auth_headers(make_user())
    weekday_slots = _get_slots(client, headers, WEEKDAY)
    assert [(s["time"], s["end_time"]) for s in weekday_slots] == [("08:00", "09:00")]

    weekend_slots = _get_slots(client, headers, WEEKEND)
    assert [s["time"] for s in weekend_slots] == ["10:00", "11:00"]


def test_레거시_문자열_슬롯설정은_2시간_블록으로_해석(
    client, db, facilities, make_user, auth_headers
):
    """구버전 설정 형식(문자열 배열) 호환 경로."""
    db.add(
        models.SystemSetting(
            key="golf_settings",
            value=json.dumps({"weekday_slots": ["13:00"], "weekend_start": 9, "weekend_end": 18}),
        )
    )
    db.commit()

    slots = _get_slots(client, auth_headers(make_user()), WEEKDAY)
    assert [(s["time"], s["end_time"]) for s in slots] == [("13:00", "15:00")]


def test_설정_조회와_변경은_관리자_전용(client, facilities, make_user, auth_headers):
    user = make_user()
    admin = make_user(role="admin")

    assert client.get("/api/golf/settings", headers=auth_headers(user)).status_code == 400
    assert client.get("/api/golf/settings", headers=auth_headers(admin)).status_code == 200

    new_settings = {
        "weekday_slots": [{"start": "07:00", "end": "08:00"}],
        "weekend_start": 8,
        "weekend_end": 9,
    }
    res = client.post("/api/golf/settings", headers=auth_headers(admin), json=new_settings)
    assert res.status_code == 200
    assert client.get("/api/golf/settings", headers=auth_headers(admin)).json() == new_settings


def test_관리자_예약목록_조회(client, db, facilities, make_user, auth_headers):
    owner = make_user(name="김직원", department="개발팀")
    start = datetime.fromisoformat(f"{WEEKDAY}T10:00:00")
    db.add(
        models.Reservation(
            user_id=owner.id,
            facility_id=facilities["golf"].id,
            start_time=start,
            end_time=start + timedelta(hours=2),
            participant_count=2,
            companions="이고객",
            status="reserved",
            priority=2,
        )
    )
    db.commit()

    admin = make_user(role="admin")
    res = client.get(
        f"/api/golf/admin/reservations?date={WEEKDAY}", headers=auth_headers(admin)
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["user_name"] == "김직원"
    assert body[0]["user_dept"] == "개발팀"
    assert body[0]["companions"] == "이고객"
    assert body[0]["priority"] == 2

    # 일반 사용자는 접근 불가
    assert (
        client.get("/api/golf/admin/reservations", headers=auth_headers(make_user())).status_code
        == 400
    )
