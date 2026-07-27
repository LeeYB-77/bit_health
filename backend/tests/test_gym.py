# 헬스장 현황 조회(혼잡도 경계값)와 입퇴실 토글의 현재 동작을 고정하는 테스트
from datetime import datetime

import pytest

from app import models


def _check_in(db, user, facility):
    db.add(models.AccessLog(user_id=user.id, facility_id=facility.id, check_in_time=datetime.now()))
    db.commit()


def test_gym_status_초기값은_비어있음(client, facilities, make_user, auth_headers):
    user = make_user()
    res = client.get("/api/gym/status", headers=auth_headers(user))
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 0
    assert body["capacity"] == 15
    assert body["congestion"] == "low"
    assert body["my_status"] == "out"


# 정원 15명 기준: 50%=7.5명 이상 medium, 80%=12명 이상 high
@pytest.mark.parametrize(
    "active_count, expected",
    [
        (0, "low"),
        (7, "low"),      # 7 < 7.5
        (8, "medium"),   # 8 >= 7.5
        (11, "medium"),  # 11 < 12
        (12, "high"),    # 12 >= 12
        (15, "high"),
    ],
)
def test_gym_혼잡도_경계값(client, db, facilities, make_user, auth_headers, active_count, expected):
    for _ in range(active_count):
        _check_in(db, make_user(), facilities["gym"])

    viewer = make_user()
    res = client.get("/api/gym/status", headers=auth_headers(viewer))
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == active_count
    assert body["congestion"] == expected


def test_gym_입퇴실_토글(client, facilities, make_user, auth_headers):
    user = make_user()
    headers = auth_headers(user)

    res = client.post("/api/gym/access", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "in"
    assert client.get("/api/gym/status", headers=headers).json()["my_status"] == "in"

    res = client.post("/api/gym/access", headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "out"
    assert client.get("/api/gym/status", headers=headers).json()["my_status"] == "out"


def test_gym_내_입실은_다른사람_카운트에_포함(client, db, facilities, make_user, auth_headers):
    other = make_user()
    _check_in(db, other, facilities["gym"])

    me = make_user()
    body = client.get("/api/gym/status", headers=auth_headers(me)).json()
    assert body["count"] == 1
    assert body["my_status"] == "out"


def test_gym_퇴실한_사용자는_카운트에서_제외(client, db, facilities, make_user, auth_headers):
    user = make_user()
    log = models.AccessLog(
        user_id=user.id,
        facility_id=facilities["gym"].id,
        check_in_time=datetime.now(),
        check_out_time=datetime.now(),
    )
    db.add(log)
    db.commit()

    body = client.get("/api/gym/status", headers=auth_headers(user)).json()
    assert body["count"] == 0
    assert body["my_status"] == "out"


def test_인증없이_조회하면_401(client, facilities):
    assert client.get("/api/gym/status").status_code == 401
