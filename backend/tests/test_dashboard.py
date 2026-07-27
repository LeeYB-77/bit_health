# 사용자 대시보드 통계(월간 이용 횟수, 오늘 예약 여부)의 동작을 고정하는 테스트
#
# Phase 5 이전에는 users.py가 tz-aware KST datetime을 naive 컬럼과 비교했다.
# SQLite는 tzinfo를 무시해 이 문제가 여기서는 드러나지 않았지만, PostgreSQL은
# naive 컬럼에 맞춰 tzinfo를 버리는 과정에서 값이 9시간 어긋날 수 있었다.
# Phase 5에서 naive datetime.now()로 통일했다. 최종 확인은 Phase 7에서
# 실제 PostgreSQL로 진행한다.
from datetime import datetime, timedelta

from app import models


def _log(db, user, facility, when):
    db.add(
        models.AccessLog(user_id=user.id, facility_id=facility.id, check_in_time=when)
    )
    db.commit()


def _dashboard(client, headers):
    res = client.get("/api/users/me/dashboard", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_초기_대시보드는_0(client, facilities, make_user, auth_headers):
    body = _dashboard(client, auth_headers(make_user()))
    assert body["monthly_count"] == 0
    assert body["has_today_reservation"] is False


def test_월간_이용횟수는_헬스와_골프를_합산(client, db, facilities, make_user, auth_headers):
    user = make_user()
    now = datetime.now()
    _log(db, user, facilities["gym"], now)
    _log(db, user, facilities["gym"], now - timedelta(hours=2))
    _log(db, user, facilities["golf"], now - timedelta(hours=3))

    assert _dashboard(client, auth_headers(user))["monthly_count"] == 3


def test_이전달_기록은_월간횟수에서_제외(client, db, facilities, make_user, auth_headers):
    user = make_user()
    _log(db, user, facilities["gym"], datetime.now())
    # 40일 전은 반드시 이전 달 이하에 속한다
    _log(db, user, facilities["gym"], datetime.now() - timedelta(days=40))

    assert _dashboard(client, auth_headers(user))["monthly_count"] == 1


def test_타인_기록은_월간횟수에서_제외(client, db, facilities, make_user, auth_headers):
    user = make_user()
    _log(db, make_user(), facilities["gym"], datetime.now())

    assert _dashboard(client, auth_headers(user))["monthly_count"] == 0


def test_오늘_예약이_있으면_True(client, db, facilities, make_user, auth_headers):
    user = make_user()
    today_noon = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    db.add(
        models.Reservation(
            user_id=user.id,
            facility_id=facilities["golf"].id,
            start_time=today_noon,
            end_time=today_noon + timedelta(hours=1),
            participant_count=1,
            status="reserved",
            priority=1,
        )
    )
    db.commit()

    assert _dashboard(client, auth_headers(user))["has_today_reservation"] is True


def test_내일_예약은_오늘_예약이_아님(client, db, facilities, make_user, auth_headers):
    user = make_user()
    tomorrow = (datetime.now() + timedelta(days=1)).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    db.add(
        models.Reservation(
            user_id=user.id,
            facility_id=facilities["golf"].id,
            start_time=tomorrow,
            end_time=tomorrow + timedelta(hours=1),
            participant_count=1,
            status="reserved",
            priority=1,
        )
    )
    db.commit()

    assert _dashboard(client, auth_headers(user))["has_today_reservation"] is False


def test_취소된_오늘_예약은_False(client, db, facilities, make_user, auth_headers):
    user = make_user()
    today_noon = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    db.add(
        models.Reservation(
            user_id=user.id,
            facility_id=facilities["golf"].id,
            start_time=today_noon,
            end_time=today_noon + timedelta(hours=1),
            participant_count=1,
            status="canceled",
            priority=1,
        )
    )
    db.commit()

    assert _dashboard(client, auth_headers(user))["has_today_reservation"] is False
