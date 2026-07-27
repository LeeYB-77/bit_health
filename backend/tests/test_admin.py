# 관리자 대시보드(통계, 현재 이용자, 이용 이력)의 현재 동작을 고정하는 테스트
from datetime import date, datetime, timedelta

from app import models


def _log(db, user, facility, when, out=None):
    db.add(
        models.AccessLog(
            user_id=user.id,
            facility_id=facility.id,
            check_in_time=when,
            check_out_time=out,
        )
    )
    db.commit()


def test_통계는_전체회원과_현재이용자수(client, db, facilities, make_user, auth_headers):
    admin = make_user(role="admin")
    a, b, c = make_user(), make_user(), make_user()

    _log(db, a, facilities["gym"], datetime.now())
    _log(db, b, facilities["gym"], datetime.now())
    _log(db, c, facilities["golf"], datetime.now())
    # 퇴실한 기록은 현재 이용자에서 제외
    _log(db, a, facilities["gym"], datetime.now() - timedelta(days=1), out=datetime.now())

    res = client.get("/api/admin/dashboard/stats", headers=auth_headers(admin))
    assert res.status_code == 200
    body = res.json()
    assert body["total_users"] == 4  # admin 포함
    assert body["current_gym_users"] == 2
    assert body["current_golf_users"] == 1


def test_통계는_관리자_전용(client, facilities, make_user, auth_headers):
    assert (
        client.get("/api/admin/dashboard/stats", headers=auth_headers(make_user())).status_code
        == 403
    )


def test_현재_이용자_목록(client, db, facilities, make_user, auth_headers):
    admin = make_user(role="admin")
    gym_user = make_user(name="헬스이용자")
    golf_user = make_user(name="골프이용자")

    _log(db, gym_user, facilities["gym"], datetime.now())
    _log(db, golf_user, facilities["golf"], datetime.now())

    res = client.get("/api/admin/dashboard/current-users", headers=auth_headers(admin))
    assert res.status_code == 200
    body = res.json()
    by_name = {u["name"]: u["type"] for u in body}
    assert by_name == {"헬스이용자": "Health", "골프이용자": "Screen Golf"}


def test_이용이력_이번주는_7일치_반환(client, db, facilities, make_user, auth_headers):
    admin = make_user(role="admin")
    res = client.get(
        "/api/admin/dashboard/usage-history?period=this_week", headers=auth_headers(admin)
    )
    assert res.status_code == 200
    assert len(res.json()) == 7


def test_이용이력은_같은날_같은사용자를_중복집계하지_않음(
    client, db, facilities, make_user, auth_headers
):
    admin = make_user(role="admin")
    user = make_user(name="반복이용자")

    # 이번 주 월요일 정오 기준으로 같은 사용자가 두 번 입실
    monday = date.today() - timedelta(days=date.today().weekday())
    noon = datetime.combine(monday, datetime.min.time()) + timedelta(hours=12)
    _log(db, user, facilities["gym"], noon)
    _log(db, user, facilities["gym"], noon + timedelta(hours=3))

    res = client.get(
        "/api/admin/dashboard/usage-history?period=this_week", headers=auth_headers(admin)
    )
    monday_row = res.json()[0]
    assert monday_row["health"] == 1, "동일 사용자는 1명으로 집계된다"
    assert monday_row["health_users"] == ["반복이용자"]


def test_이용이력_월간은_1일부터_말일까지(client, facilities, make_user, auth_headers):
    admin = make_user(role="admin")
    res = client.get(
        "/api/admin/dashboard/usage-history?period=month", headers=auth_headers(admin)
    )
    assert res.status_code == 200
    body = res.json()

    today = date.today()
    if today.month == 12:
        next_month_first = date(today.year + 1, 1, 1)
    else:
        next_month_first = date(today.year, today.month + 1, 1)
    days_in_month = (next_month_first - date(today.year, today.month, 1)).days

    assert len(body) == days_in_month
    assert body[0]["name"] == "1일"
    assert body[-1]["name"] == f"{days_in_month}일"
