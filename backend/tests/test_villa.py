# 비트별장 신청·조회 API와 성수기 연박 제한, 겹침 판정을 고정하는 테스트
import json
from datetime import date, datetime, timedelta

import pytest

from app import models
from app.routers import villa as villa_router
from villa_helpers import in_target_month, payload, seed, target_month


# 공용 헬퍼는 villa_helpers 모듈에 있다. 기존 호출부 이름을 유지하기 위해 별칭을 둔다.
_target_month = target_month
_in_target_month = in_target_month
_payload = payload
_seed = seed


@pytest.fixture
def set_villa_settings(db):
    """villa_settings를 덮어쓴다. 성수기 규칙을 오늘 날짜와 무관하게 만들기 위해 쓴다."""
    def _set(**overrides):
        settings = dict(villa_router.DEFAULT_VILLA_SETTINGS)
        settings.update(overrides)
        row = db.query(models.SystemSetting).filter(
            models.SystemSetting.key == "villa_settings"
        ).first()
        if row:
            row.value = json.dumps(settings, ensure_ascii=False)
        else:
            db.add(models.SystemSetting(
                key="villa_settings", value=json.dumps(settings, ensure_ascii=False)
            ))
        db.commit()
        return settings
    return _set


# --- 날짜 계산 단위 테스트 ---

@pytest.mark.parametrize(
    "year, month, delta, expected",
    [
        (2026, 10, -2, (2026, 8)),
        (2026, 1, -2, (2025, 11)),
        (2026, 12, 1, (2027, 1)),
        (2026, 7, 2, (2026, 9)),
        (2026, 11, 2, (2027, 1)),
    ],
)
def test_shift_month(year, month, delta, expected):
    assert villa_router.shift_month(year, month, delta) == expected


def test_접수기간은_대상월_2개월_전_1일부터_말일까지():
    apply_start, apply_end, notify_date = villa_router.apply_window_for_target(2026, 10)
    assert apply_start == date(2026, 8, 1)
    assert apply_end == date(2026, 8, 31)
    assert notify_date == date(2026, 8, 31)  # 통보일은 마감일과 같다


def test_접수기간_연말_경계():
    # 2026년 1월 대상 → 2025년 11월 접수
    apply_start, apply_end, _ = villa_router.apply_window_for_target(2026, 1)
    assert apply_start == date(2025, 11, 1)
    assert apply_end == date(2025, 11, 30)


# --- 성수기 연박 제한 (오늘 날짜와 무관한 단위 테스트) ---

PEAK_SETTINGS = {"peak_months": [7, 8], "peak_max_nights": 2, "default_max_nights": None}


@pytest.mark.parametrize(
    "start, end, nights, allowed",
    [
        # 성수기 안: 2박 허용, 3박 거부
        (date(2026, 7, 10), date(2026, 7, 12), 2, True),
        (date(2026, 7, 10), date(2026, 7, 13), 3, False),
        # 성수기 걸침: 6월 체크인이어도 7월을 포함하면 제한 적용
        (date(2026, 6, 30), date(2026, 7, 3), 3, False),
        (date(2026, 6, 30), date(2026, 7, 2), 2, True),
        # 8월 → 9월 걸침
        (date(2026, 8, 30), date(2026, 9, 2), 3, False),
        # 비성수기: 제한 없음
        (date(2026, 6, 25), date(2026, 6, 28), 3, True),
        (date(2026, 9, 1), date(2026, 9, 8), 7, True),
    ],
)
def test_성수기_연박_제한_판정(start, end, nights, allowed):
    assert villa_router.nights_of(start, end) == nights
    max_nights = villa_router.max_nights_for(start, end, PEAK_SETTINGS)
    if allowed:
        assert max_nights is None or nights <= max_nights
    else:
        assert max_nights is not None and nights > max_nights


def test_성수기_판정은_체크아웃_월도_포함():
    assert villa_router.months_spanned(date(2026, 6, 30), date(2026, 7, 1)) == {6, 7}
    assert villa_router.months_spanned(date(2026, 6, 25), date(2026, 6, 28)) == {6}


# --- 조회 API ---

def test_별장_목록_조회(client, facilities, make_user, auth_headers):
    res = client.get("/api/villa/facilities", headers=auth_headers(make_user()))
    assert res.status_code == 200
    body = res.json()
    assert [v["name"] for v in body] == ["청평별장", "동비재"]
    assert all(v["capacity"] == 20 for v in body)
    assert body[0]["default_checkin_time"] == "14:00"
    assert body[0]["default_checkout_time"] == "12:00"


def test_현재_회차는_2개월_뒤_대상월(client, facilities, make_user, auth_headers):
    res = client.get("/api/villa/current-round", headers=auth_headers(make_user()))
    assert res.status_code == 200
    body = res.json()

    ty, tm = _target_month()
    assert (body["target_year"], body["target_month"]) == (ty, tm)

    # 접수 기간은 항상 '이번 달 1일~말일'이 된다
    today = datetime.now().date()
    assert body["apply_start"] == date(today.year, today.month, 1).isoformat()
    assert body["notify_date"] == body["apply_end"]
    assert body["is_open"] is True


def test_인증없이_조회하면_401(client, facilities):
    assert client.get("/api/villa/facilities").status_code == 401
    assert client.get("/api/villa/current-round").status_code == 401


# --- 신청 ---

def test_신청_성공(client, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    start, end = _in_target_month(10), _in_target_month(12)

    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(villa.id, start, end, participant_count=6),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "applied"
    assert body["booking_type"] == "regular"
    assert body["start_date"] == start.isoformat()
    assert body["participant_count"] == 6
    assert body["round_id"] is not None


def test_신청시_회차가_자동_생성(client, db, facilities, make_user, auth_headers):
    assert db.query(models.VillaBookingRound).count() == 0

    client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(facilities["cheongpyeong"].id, _in_target_month(10), _in_target_month(12)),
    )

    rounds = db.query(models.VillaBookingRound).all()
    assert len(rounds) == 1
    ty, tm = _target_month()
    assert (rounds[0].target_year, rounds[0].target_month) == (ty, tm)

    # 두 번째 신청은 같은 회차를 재사용한다
    client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(facilities["cheongpyeong"].id, _in_target_month(20), _in_target_month(22)),
    )
    assert db.query(models.VillaBookingRound).count() == 1


def test_없는_별장은_404(client, facilities, make_user, auth_headers):
    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(99999, _in_target_month(10), _in_target_month(12)),
    )
    assert res.status_code == 404


def test_골프_시설로는_신청_불가(client, facilities, make_user, auth_headers):
    """type이 villa가 아닌 시설은 거부한다."""
    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(facilities["golf"].id, _in_target_month(10), _in_target_month(12)),
    )
    assert res.status_code == 404


@pytest.mark.parametrize("start_day, end_day", [(12, 10), (10, 10)])
def test_체크아웃이_체크인_이후가_아니면_400(
    client, facilities, make_user, auth_headers, start_day, end_day
):
    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(facilities["cheongpyeong"].id, _in_target_month(start_day), _in_target_month(end_day)),
    )
    assert res.status_code == 400
    assert "최소 1박" in res.json()["detail"]


def test_지난_날짜는_400(client, facilities, make_user, auth_headers):
    today = datetime.now().date()
    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(facilities["cheongpyeong"].id, today - timedelta(days=3), today - timedelta(days=1)),
    )
    assert res.status_code == 400


def test_정원_초과는_400(client, facilities, make_user, auth_headers):
    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(facilities["cheongpyeong"].id, _in_target_month(10), _in_target_month(12), participant_count=21),
    )
    assert res.status_code == 400
    assert "정원은 20명" in res.json()["detail"]


def test_정원_경계값_20명은_허용(client, facilities, make_user, auth_headers):
    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(facilities["cheongpyeong"].id, _in_target_month(10), _in_target_month(12), participant_count=20),
    )
    assert res.status_code == 200, res.text


def test_대상월이_아니면_400(client, facilities, make_user, auth_headers):
    """다음 회차(3개월 뒤) 날짜는 아직 접수 대상이 아니다."""
    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(facilities["cheongpyeong"].id, _in_target_month(10, 1), _in_target_month(12, 1)),
    )
    assert res.status_code == 400
    assert "접수중인 대상월" in res.json()["detail"]


def test_성수기_연박_제한_API(client, facilities, make_user, auth_headers, set_villa_settings):
    """현재 대상월을 성수기로 지정해 API 경로에서 제한이 걸리는지 확인한다."""
    _, tm = _target_month()
    set_villa_settings(peak_months=[tm], peak_max_nights=2)
    villa = facilities["cheongpyeong"]
    headers = auth_headers(make_user())

    # 3박 → 거부
    res = client.post(
        "/api/villa/apply",
        headers=headers,
        json=_payload(villa.id, _in_target_month(10), _in_target_month(13)),
    )
    assert res.status_code == 400
    assert "최대 2박" in res.json()["detail"]

    # 2박 → 허용
    res = client.post(
        "/api/villa/apply",
        headers=headers,
        json=_payload(villa.id, _in_target_month(10), _in_target_month(12)),
    )
    assert res.status_code == 200, res.text


def test_비성수기는_연박_제한_없음(client, facilities, make_user, auth_headers, set_villa_settings):
    _, tm = _target_month()
    other_month = 1 if tm != 1 else 2
    set_villa_settings(peak_months=[other_month], peak_max_nights=2, default_max_nights=None)

    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(facilities["cheongpyeong"].id, _in_target_month(5), _in_target_month(12)),
    )
    assert res.status_code == 200, res.text


# --- 중복 신청과 겹침 판정 ---

def test_타인과_같은_기간_중복_신청_허용(client, db, facilities, make_user, auth_headers):
    """정규예약은 중복 신청을 허용하고 관리자가 선택한다."""
    villa = facilities["cheongpyeong"]
    start, end = _in_target_month(10), _in_target_month(12)

    for _ in range(3):
        res = client.post(
            "/api/villa/apply",
            headers=auth_headers(make_user()),
            json=_payload(villa.id, start, end),
        )
        assert res.status_code == 200, res.text

    assert db.query(models.VillaReservation).filter(
        models.VillaReservation.status == "applied"
    ).count() == 3


def test_본인_중복_신청은_400(client, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    headers = auth_headers(make_user())
    start, end = _in_target_month(10), _in_target_month(12)

    assert client.post("/api/villa/apply", headers=headers, json=_payload(villa.id, start, end)).status_code == 200
    res = client.post("/api/villa/apply", headers=headers, json=_payload(villa.id, start, end))
    assert res.status_code == 400
    assert "이미 해당 기간에 신청" in res.json()["detail"]


def test_확정된_기간과_겹치면_409(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    _seed(db, make_user(), villa, _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(villa.id, _in_target_month(11), _in_target_month(13)),
    )
    assert res.status_code == 409


def test_체크아웃일에_체크인하면_겹치지_않음(client, db, facilities, make_user, auth_headers):
    """체크아웃 날짜는 배타적이다. 10일~12일 확정 상태에서 12일~14일 신청은 가능하다."""
    villa = facilities["cheongpyeong"]
    _seed(db, make_user(), villa, _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(villa.id, _in_target_month(12), _in_target_month(14)),
    )
    assert res.status_code == 200, res.text


def test_취소요청_상태도_기간을_점유(client, db, facilities, make_user, auth_headers):
    """관리자 승인 전까지는 여전히 확정 상태로 본다."""
    villa = facilities["cheongpyeong"]
    _seed(db, make_user(), villa, _in_target_month(10), _in_target_month(12), status="cancel_requested")

    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(villa.id, _in_target_month(10), _in_target_month(12)),
    )
    assert res.status_code == 409


@pytest.mark.parametrize("dead_status", ["canceled", "rejected"])
def test_취소_미선정_예약은_기간을_점유하지_않음(
    client, db, facilities, make_user, auth_headers, dead_status
):
    villa = facilities["cheongpyeong"]
    _seed(db, make_user(), villa, _in_target_month(10), _in_target_month(12), status=dead_status)

    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(villa.id, _in_target_month(10), _in_target_month(12)),
    )
    assert res.status_code == 200, res.text


def test_다른_별장은_서로_영향_없음(client, db, facilities, make_user, auth_headers):
    _seed(db, make_user(), facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.post(
        "/api/villa/apply",
        headers=auth_headers(make_user()),
        json=_payload(facilities["dongbijae"].id, _in_target_month(10), _in_target_month(12)),
    )
    assert res.status_code == 200, res.text


# --- 달력 ---

def test_달력_조회(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    ty, tm = _target_month()
    owner = make_user(name="김직원", department="개발팀")
    _seed(db, owner, villa, _in_target_month(10), _in_target_month(12), status="confirmed", participant_count=6)

    viewer = make_user()
    res = client.get(
        f"/api/villa/calendar?facility_id={villa.id}&year={ty}&month={tm}",
        headers=auth_headers(viewer),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["facility_name"] == "청평별장"
    assert body["capacity"] == 20
    assert len(body["items"]) == 1

    item = body["items"][0]
    assert item["status"] == "confirmed"
    assert item["nights"] == 2
    assert item["user_name"] == "김직원"   # 확정 건은 이름을 공개한다
    assert item["is_mine"] is False


def test_달력에서_경합중인_신청은_신청자를_숨김(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    ty, tm = _target_month()
    other = make_user(name="박사원")
    me = make_user(name="나")
    _seed(db, other, villa, _in_target_month(10), _in_target_month(12), status="applied")
    _seed(db, me, villa, _in_target_month(10), _in_target_month(12), status="applied")

    res = client.get(
        f"/api/villa/calendar?facility_id={villa.id}&year={ty}&month={tm}",
        headers=auth_headers(me),
    )
    items = res.json()["items"]
    assert len(items) == 2

    by_mine = {item["is_mine"]: item for item in items}
    assert by_mine[True]["user_name"] == "나"      # 본인 것은 보인다
    assert by_mine[False]["user_name"] is None     # 타인의 경합 신청은 숨긴다


@pytest.mark.parametrize("hidden_status", ["canceled", "rejected"])
def test_달력은_취소_미선정을_제외(client, db, facilities, make_user, auth_headers, hidden_status):
    villa = facilities["cheongpyeong"]
    ty, tm = _target_month()
    _seed(db, make_user(), villa, _in_target_month(10), _in_target_month(12), status=hidden_status)

    res = client.get(
        f"/api/villa/calendar?facility_id={villa.id}&year={ty}&month={tm}",
        headers=auth_headers(make_user()),
    )
    assert res.json()["items"] == []


def test_달력은_월을_걸치는_예약도_포함(client, db, facilities, make_user, auth_headers):
    """10/31~11/2 예약은 10월과 11월 달력에 모두 나타난다."""
    villa = facilities["cheongpyeong"]
    ty, tm = _target_month()
    last_day = 28  # 모든 달에 존재하는 날짜로 안전하게 잡는다
    ny, nm = villa_router.shift_month(ty, tm, 1)

    _seed(
        db, make_user(), villa,
        date(ty, tm, last_day), date(ny, nm, 2),
        status="confirmed",
    )

    headers = auth_headers(make_user())
    this_month = client.get(f"/api/villa/calendar?facility_id={villa.id}&year={ty}&month={tm}", headers=headers)
    next_month = client.get(f"/api/villa/calendar?facility_id={villa.id}&year={ny}&month={nm}", headers=headers)

    assert len(this_month.json()["items"]) == 1
    assert len(next_month.json()["items"]) == 1


def test_달력_잘못된_month는_400(client, facilities, make_user, auth_headers):
    res = client.get(
        f"/api/villa/calendar?facility_id={facilities['cheongpyeong'].id}&year=2026&month=13",
        headers=auth_headers(make_user()),
    )
    assert res.status_code == 400


# --- 내 신청 목록 ---

def test_내_신청_목록(client, db, facilities, make_user, auth_headers):
    villa = facilities["cheongpyeong"]
    me = make_user()
    _seed(db, me, villa, _in_target_month(10), _in_target_month(12), status="confirmed")
    _seed(db, make_user(), villa, _in_target_month(20), _in_target_month(22), status="applied")

    body = client.get("/api/villa/my", headers=auth_headers(me)).json()
    assert len(body) == 1
    assert body[0]["facility_name"] == "청평별장"
    assert body[0]["status"] == "confirmed"
    assert body[0]["nights"] == 2
    # 확정됐지만 추가입력을 안 했으므로 True
    assert body[0]["needs_extra_info"] is True


def test_추가입력을_마치면_needs_extra_info가_False(client, db, facilities, make_user, auth_headers):
    me = make_user()
    row = _seed(db, me, facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status="confirmed")
    row.extra_info_updated_at = datetime.now()
    db.commit()

    body = client.get("/api/villa/my", headers=auth_headers(me)).json()
    assert body[0]["needs_extra_info"] is False


# --- 취소 ---

def test_applied_신청은_즉시_취소(client, db, facilities, make_user, auth_headers):
    me = make_user()
    row = _seed(db, me, facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status="applied")

    res = client.post(f"/api/villa/cancel/{row.id}", headers=auth_headers(me))
    assert res.status_code == 200
    db.refresh(row)
    assert row.status == "canceled"
    assert row.canceled_at is not None
    assert row.canceled_by == me.id


def test_confirmed는_즉시_취소_거부(client, db, facilities, make_user, auth_headers):
    me = make_user()
    row = _seed(db, me, facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.post(f"/api/villa/cancel/{row.id}", headers=auth_headers(me))
    assert res.status_code == 400
    assert "관리자 승인" in res.json()["detail"]
    db.refresh(row)
    assert row.status == "confirmed"


def test_타인_신청_취소는_403(client, db, facilities, make_user, auth_headers):
    row = _seed(db, make_user(), facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12))

    res = client.post(f"/api/villa/cancel/{row.id}", headers=auth_headers(make_user()))
    assert res.status_code == 403


def test_관리자는_타인_신청도_취소_가능(client, db, facilities, make_user, auth_headers):
    row = _seed(db, make_user(), facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12))

    res = client.post(f"/api/villa/cancel/{row.id}", headers=auth_headers(make_user(role="admin")))
    assert res.status_code == 200


def test_없는_신청_취소는_404(client, facilities, make_user, auth_headers):
    assert client.post("/api/villa/cancel/99999", headers=auth_headers(make_user())).status_code == 404


# --- 취소 요청 (확정 후) ---

def test_확정_예약_취소_요청(client, db, facilities, make_user, auth_headers):
    me = make_user()
    row = _seed(db, me, facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.post(
        f"/api/villa/cancel-request/{row.id}",
        headers=auth_headers(me),
        json={"reason": "개인 사정"},
    )
    assert res.status_code == 200
    db.refresh(row)
    assert row.status == "cancel_requested"
    assert row.cancel_requested_at is not None
    assert row.cancel_reason == "개인 사정"


def test_취소_사유는_선택_입력(client, db, facilities, make_user, auth_headers):
    me = make_user()
    row = _seed(db, me, facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.post(f"/api/villa/cancel-request/{row.id}", headers=auth_headers(me), json={})
    assert res.status_code == 200
    db.refresh(row)
    assert row.status == "cancel_requested"
    assert row.cancel_reason is None


def test_applied에_취소요청은_400(client, db, facilities, make_user, auth_headers):
    me = make_user()
    row = _seed(db, me, facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status="applied")

    res = client.post(f"/api/villa/cancel-request/{row.id}", headers=auth_headers(me), json={})
    assert res.status_code == 400
    assert "확정된 예약만" in res.json()["detail"]


def test_타인_예약_취소요청은_403(client, db, facilities, make_user, auth_headers):
    row = _seed(db, make_user(), facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.post(f"/api/villa/cancel-request/{row.id}", headers=auth_headers(make_user()), json={})
    assert res.status_code == 403


def test_관리자에게_취소요청_알림_시도(client, db, facilities, make_user, auth_headers, monkeypatch):
    """SLACK_BOT_TOKEN이 없어도 예외 없이 통과해야 한다(테스트 환경 기본)."""
    sent = []
    monkeypatch.setattr(
        villa_router.slack_utils,
        "notify_villa_cancel_request",
        lambda **kwargs: sent.append(kwargs),
    )

    make_user(role="admin", email="admin1@bit.kr")
    make_user(role="admin", email="admin2@bit.kr")
    make_user(role="admin", email=None)  # 이메일 없는 관리자는 건너뛴다

    me = make_user(name="신청자")
    row = _seed(db, me, facilities["cheongpyeong"], _in_target_month(10), _in_target_month(12), status="confirmed")

    res = client.post(
        f"/api/villa/cancel-request/{row.id}",
        headers=auth_headers(me),
        json={"reason": "일정 변경"},
    )
    assert res.status_code == 200
    assert len(sent) == 2
    assert {s["email"] for s in sent} == {"admin1@bit.kr", "admin2@bit.kr"}
    assert sent[0]["applicant_name"] == "신청자"
    assert sent[0]["villa_name"] == "청평별장"
    assert sent[0]["reason"] == "일정 변경"
