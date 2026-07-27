# 골프 예약의 우선순위 선점 규칙, 3시간 제한, 다중 슬롯 2-패스 동작을 고정하는 테스트
from datetime import datetime, timedelta

import pytest

from app import models


def _slot(hour, days=1):
    """오늘로부터 days일 뒤 정시. 항상 현재보다 최소 10시간 이후가 되어 3시간 제한을 피한다."""
    return (datetime.now() + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


def _reserve_in_db(db, user, golf, start, end, priority, status="reserved"):
    res = models.Reservation(
        user_id=user.id,
        facility_id=golf.id,
        start_time=start,
        end_time=end,
        participant_count=1,
        status=status,
        priority=priority,
    )
    db.add(res)
    db.commit()
    db.refresh(res)
    return res


def _payload(start, end, priority, participant_count=1, companions=None):
    return {
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "participant_count": participant_count,
        "companions": companions,
        "priority": priority,
    }


def test_빈_슬롯_예약_성공(client, facilities, make_user, auth_headers):
    user = make_user()
    start, end = _slot(10), _slot(11)
    res = client.post(
        "/api/golf/reserve", headers=auth_headers(user), json=_payload(start, end, 2)
    )
    assert res.status_code == 200
    body = res.json()
    assert body["priority"] == 2
    assert body["status"] == "reserved"


# 숫자가 낮을수록 높은 우선순위(1 최우선 > 2 우선 > 3 양보).
# 엔드포인트 조건은 `priority >= existing.priority`면 거부이므로 동급끼리는 선점 불가다.
@pytest.mark.parametrize(
    "mine, existing, allowed",
    [
        (1, 1, False),
        (1, 2, True),
        (1, 3, True),
        (2, 1, False),
        (2, 2, False),
        (2, 3, True),
        (3, 1, False),
        (3, 2, False),
        (3, 3, False),
    ],
)
def test_선점_우선순위_매트릭스(
    client, db, facilities, make_user, auth_headers, mine, existing, allowed
):
    golf = facilities["golf"]
    start, end = _slot(10), _slot(11)

    owner = make_user(email="owner@bit.kr")
    old = _reserve_in_db(db, owner, golf, start, end, existing)

    me = make_user()
    res = client.post(
        "/api/golf/reserve", headers=auth_headers(me), json=_payload(start, end, mine)
    )

    db.refresh(old)
    if allowed:
        assert res.status_code == 200, res.text
        assert old.status == "canceled"
    else:
        assert res.status_code == 409, res.text
        assert old.status == "reserved"


def test_본인_중복_예약은_400(client, db, facilities, make_user, auth_headers):
    user = make_user()
    start, end = _slot(10), _slot(11)
    _reserve_in_db(db, user, facilities["golf"], start, end, 1)

    res = client.post(
        "/api/golf/reserve", headers=auth_headers(user), json=_payload(start, end, 1)
    )
    assert res.status_code == 400
    assert "본인" in res.json()["detail"]


def test_시작_3시간_이내_타인예약은_선점_불가(client, db, facilities, make_user, auth_headers):
    """우선순위가 더 높아도 시작 3시간 이내면 교체할 수 없다."""
    now = datetime.now()
    start = (now + timedelta(hours=2)).replace(second=0, microsecond=0)
    end = start + timedelta(hours=1)

    owner = make_user(email="owner@bit.kr")
    old = _reserve_in_db(db, owner, facilities["golf"], start, end, 3)

    me = make_user()
    res = client.post(
        "/api/golf/reserve", headers=auth_headers(me), json=_payload(start, end, 1)
    )

    assert res.status_code == 400
    assert "3시간" in res.json()["detail"]
    db.refresh(old)
    assert old.status == "reserved"


def test_시작_3시간_초과면_선점_가능(client, db, facilities, make_user, auth_headers):
    now = datetime.now()
    start = (now + timedelta(hours=4)).replace(second=0, microsecond=0)
    end = start + timedelta(hours=1)

    owner = make_user(email="owner@bit.kr")
    old = _reserve_in_db(db, owner, facilities["golf"], start, end, 3)

    me = make_user()
    res = client.post(
        "/api/golf/reserve", headers=auth_headers(me), json=_payload(start, end, 1)
    )

    assert res.status_code == 200, res.text
    db.refresh(old)
    assert old.status == "canceled"


def test_다중슬롯_일부_거부되면_아무것도_취소되지_않음(
    client, db, facilities, make_user, auth_headers
):
    """
    2-패스 구조의 핵심 보장. 10-12시를 '우선'(2)으로 예약 시도할 때
    10-11시는 '양보'(3, 선점 가능), 11-12시는 '최우선'(1, 선점 불가)이면
    전체가 거부되고 두 예약 모두 살아 있어야 한다.
    """
    golf = facilities["golf"]
    owner_a = make_user(email="a@bit.kr")
    owner_b = make_user(email="b@bit.kr")

    res_a = _reserve_in_db(db, owner_a, golf, _slot(10), _slot(11), 3)
    res_b = _reserve_in_db(db, owner_b, golf, _slot(11), _slot(12), 1)

    me = make_user()
    res = client.post(
        "/api/golf/reserve",
        headers=auth_headers(me),
        json=_payload(_slot(10), _slot(12), 2, participant_count=2, companions="홍길동"),
    )

    assert res.status_code == 409, res.text
    db.refresh(res_a)
    db.refresh(res_b)
    assert res_a.status == "reserved", "선점 가능했던 예약까지 취소되면 안 된다"
    assert res_b.status == "reserved"

    # 새 예약도 생성되지 않아야 한다
    assert (
        db.query(models.Reservation).filter(models.Reservation.user_id == me.id).count() == 0
    )


def test_다중슬롯_전부_선점가능하면_모두_취소(client, db, facilities, make_user, auth_headers):
    golf = facilities["golf"]
    owner_a = make_user(email="a@bit.kr")
    owner_b = make_user(email="b@bit.kr")

    res_a = _reserve_in_db(db, owner_a, golf, _slot(10), _slot(11), 3)
    res_b = _reserve_in_db(db, owner_b, golf, _slot(11), _slot(12), 3)

    me = make_user()
    res = client.post(
        "/api/golf/reserve",
        headers=auth_headers(me),
        json=_payload(_slot(10), _slot(12), 1, participant_count=2, companions="홍길동"),
    )

    assert res.status_code == 200, res.text
    db.refresh(res_a)
    db.refresh(res_b)
    assert res_a.status == "canceled"
    assert res_b.status == "canceled"


def test_취소된_예약은_슬롯을_점유하지_않음(client, db, facilities, make_user, auth_headers):
    owner = make_user()
    _reserve_in_db(db, owner, facilities["golf"], _slot(10), _slot(11), 1, status="canceled")

    me = make_user()
    res = client.post(
        "/api/golf/reserve", headers=auth_headers(me), json=_payload(_slot(10), _slot(11), 3)
    )
    assert res.status_code == 200, res.text


def test_2인이상_예약시_동반자_필수(client, facilities, make_user, auth_headers):
    user = make_user()
    headers = auth_headers(user)

    res = client.post(
        "/api/golf/reserve",
        headers=headers,
        json=_payload(_slot(10), _slot(11), 1, participant_count=2, companions=None),
    )
    assert res.status_code == 400
    assert "동반자" in res.json()["detail"]

    res = client.post(
        "/api/golf/reserve",
        headers=headers,
        json=_payload(_slot(10), _slot(11), 1, participant_count=2, companions="   "),
    )
    assert res.status_code == 400


def test_종료시간이_시작시간_이전이면_400(client, facilities, make_user, auth_headers):
    user = make_user()
    res = client.post(
        "/api/golf/reserve",
        headers=auth_headers(user),
        json=_payload(_slot(11), _slot(10), 1),
    )
    assert res.status_code == 400


@pytest.mark.parametrize("bad_priority", [0, 4, -1])
def test_허용되지_않는_우선순위는_400(
    client, facilities, make_user, auth_headers, bad_priority
):
    user = make_user()
    res = client.post(
        "/api/golf/reserve",
        headers=auth_headers(user),
        json=_payload(_slot(10), _slot(11), bad_priority),
    )
    assert res.status_code == 400


def test_예약_취소_권한(client, db, facilities, make_user, auth_headers):
    owner = make_user()
    stranger = make_user()
    admin = make_user(role="admin")
    golf = facilities["golf"]

    res1 = _reserve_in_db(db, owner, golf, _slot(10), _slot(11), 1)
    assert client.post(f"/api/golf/cancel/{res1.id}", headers=auth_headers(stranger)).status_code == 403
    assert client.post(f"/api/golf/cancel/{res1.id}", headers=auth_headers(owner)).status_code == 200
    db.refresh(res1)
    assert res1.status == "canceled"

    res2 = _reserve_in_db(db, owner, golf, _slot(14), _slot(15), 1)
    assert client.post(f"/api/golf/cancel/{res2.id}", headers=auth_headers(admin)).status_code == 200


def test_없는_예약_취소는_404(client, facilities, make_user, auth_headers):
    user = make_user()
    assert client.post("/api/golf/cancel/99999", headers=auth_headers(user)).status_code == 404


def test_내_예약_목록은_오늘_이후만(client, db, facilities, make_user, auth_headers):
    user = make_user()
    golf = facilities["golf"]

    past = _slot(10, days=-3)
    _reserve_in_db(db, user, golf, past, past + timedelta(hours=1), 1)
    _reserve_in_db(db, user, golf, _slot(10), _slot(11), 1)
    # 타인 예약은 포함되지 않는다
    _reserve_in_db(db, make_user(), golf, _slot(14), _slot(15), 1)

    body = client.get("/api/golf/my", headers=auth_headers(user)).json()
    assert len(body) == 1
    assert body[0]["start_time"].startswith(_slot(10).strftime("%Y-%m-%d"))


def test_골프_입퇴실_토글(client, facilities, make_user, auth_headers):
    user = make_user()
    headers = auth_headers(user)
    assert client.post("/api/golf/access", headers=headers).json()["status"] == "in"
    assert client.post("/api/golf/access", headers=headers).json()["status"] == "out"
