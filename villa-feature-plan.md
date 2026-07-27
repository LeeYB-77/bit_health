# 비트별장(휴양소) 예약 기능 기획안

작성일: 2026-07-27
대상: 청평별장(청평), 동비재(속초)

---

## 1. 확정된 설계 결정

착수 전 사용자 확인을 받은 4가지다. 이 결정이 데이터 모델과 보안 설계의 전제다.

| 항목 | 결정 |
|---|---|
| 이용 기간 | **체크인~체크아웃 날짜 범위** (연박 가능) |
| 정규예약 주기 | **대상월 2개월 전 1일~말일 접수, 말일 확정 통보** (10월 → 8/1~8/31 접수, 8/31 통보) |
| 정원 | **청평별장 20명 / 동비재 20명** |
| 연박 상한 | **7·8월은 최대 2박3일, 그 외 달은 제한 없음** |
| 확정 후 취소 | **관리자 승인 필요** (요청 → 승인 → 취소 확정) |
| SMTP 비밀번호 | **DB에 암호화 저장, 키는 `.env`** |
| 추가입력 페이지 | **SSO 로그인 필수 + 본인 예약만 접근** |

---

## 2. 기능 개요

### 예약 생애주기

```
[정규예약 접수기간]              [마감]        [통보일]
  8/1 ─────────────── 8/31 ──────────────── 8/31
   │                    │                     │
   └─ 사용자 신청       └─ 관리자 확정        └─ Slack+메일 통보
      (중복 허용)          (경합 중 선택)        + 추가입력 링크
                                                    │
[통보 후]                                           ▼
  미예약일은 선착순 신청 가능              차량/이용구성 입력
```

### 상태 정의

| status | 의미 | 다음 전이 |
|---|---|---|
| `applied` | 신청 접수. 같은 기간에 여러 건 공존 가능 | `confirmed` / `rejected` / `canceled` |
| `confirmed` | 관리자 확정 또는 선착순 즉시 확정 | `cancel_requested` |
| `cancel_requested` | 확정 후 사용자가 취소 요청. 관리자 승인 대기 | `canceled`(승인) / `confirmed`(반려) |
| `canceled` | 취소 완료. 해당 기간이 다시 열린다 | 종료 |
| `rejected` | 중복 경합에서 미선정 | 종료 |

**`applied` 상태의 취소는 관리자 승인 없이 즉시 처리한다.** 아직 확정 전이라 다른 신청자에게 영향이 없다. 관리자 승인이 필요한 것은 **확정된 예약의 취소**뿐이다.

### 취소 흐름 (확정 후)

```
사용자 취소 요청          관리자 검토
     │                       │
     ▼                       ▼
confirmed ──► cancel_requested ──┬──► canceled (승인) ──► 기간 재개방
                  │              │
            관리자에게            └──► confirmed (반려)
            Slack 알림                    │
                                    사용자에게 Slack+메일 통보
```

---

## 3. 데이터 모델

### 3-1. 별장 엔티티는 기존 `Facility`를 재사용한다

`type='villa'`로 2행을 시드한다. 새 테이블을 만들지 않는 이유는 gym/golf와 동일한 성격의 시설이고, `initial_data.py`의 기존 시드 패턴을 그대로 쓸 수 있기 때문이다.

```python
{"name": "청평별장", "type": "villa", "capacity": 20}
{"name": "동비재",   "type": "villa", "capacity": 20}
```

주소·안내문·기본 입퇴실 시간·연박 규칙 같은 부가 정보는 `SystemSetting`의 `villa_settings` JSON에 담는다. `golf_settings`와 같은 방식이다.

```json
{
  "peak_months": [7, 8],
  "peak_max_nights": 2,
  "default_max_nights": null,
  "default_checkin_time": "15:00",
  "default_checkout_time": "11:00",
  "villas": {
    "청평별장": { "address": "...", "notice": "..." },
    "동비재":   { "address": "...", "notice": "..." }
  }
}
```

성수기 규칙을 하드코딩하지 않고 설정으로 빼는 이유는 대상 월이나 박수 제한이 해마다 바뀔 수 있기 때문이다. 하드코딩하면 그때마다 코드 수정과 재배포가 필요하다. 골프도 시간대를 `golf_settings`로 뺀 것과 같은 판단이다.

> ⚠️ **주의:** [admin.py:57](backend/app/routers/admin.py:57)의 `facility_name = "Health" if log.facility.type == "gym" else "Screen Golf"`는 villa를 "Screen Golf"로 잘못 표기한다. 별장은 QR 입퇴실(`AccessLog`)을 쓰지 않으므로 현재는 도달 불가 경로지만, 향후 별장에 입퇴실 기록을 붙이면 이 분기를 먼저 고쳐야 한다.

### 3-2. 신규 테이블 — `villa_reservations`

```python
class VillaReservation(Base):
    __tablename__ = "villa_reservations"
    id                    = Column(Integer, primary_key=True, index=True)
    user_id               = Column(Integer, ForeignKey("users.id"))
    facility_id           = Column(Integer, ForeignKey("facilities.id"))

    # 이용 기간 (체크아웃 날짜는 배타적)
    start_date            = Column(Date, index=True)   # 체크인
    end_date              = Column(Date, index=True)   # 체크아웃
    checkin_time          = Column(String)             # "15:00" 예상 입실
    checkout_time         = Column(String)             # "11:00" 예상 퇴실
    participant_count     = Column(Integer)

    status                = Column(String, default="applied")
    booking_type          = Column(String)             # regular | open
    round_id              = Column(Integer, ForeignKey("villa_booking_rounds.id"), nullable=True)

    created_at            = Column(DateTime, default=datetime.now)  # KST naive
    confirmed_at          = Column(DateTime, nullable=True)
    confirmed_by          = Column(Integer, ForeignKey("users.id"), nullable=True)
    notified_confirmed    = Column(Boolean, default=False)

    # 확정 후 취소 (관리자 승인 필요)
    cancel_requested_at   = Column(DateTime, nullable=True)
    cancel_reason         = Column(Text, nullable=True)
    canceled_at           = Column(DateTime, nullable=True)
    canceled_by           = Column(Integer, ForeignKey("users.id"), nullable=True)

    # 확정 후 추가 입력사항
    vehicle_count         = Column(Integer, nullable=True)
    vehicle_numbers       = Column(Text, nullable=True)   # 쉼표 구분
    adult_count           = Column(Integer, nullable=True)
    child_count           = Column(Integer, nullable=True)  # 15세 이하
    extra_info_updated_at = Column(DateTime, nullable=True)
```

`Date` 타입을 쓰므로 Phase 5에서 정리한 타임존 문제가 재발하지 않는다. `created_at`은 KST naive(`datetime.now`)로 기존 정책과 맞춘다.

### 3-3. 신규 테이블 — `villa_booking_rounds` (정규예약 회차)

```python
class VillaBookingRound(Base):
    __tablename__ = "villa_booking_rounds"
    id           = Column(Integer, primary_key=True, index=True)
    target_year  = Column(Integer)   # 2026
    target_month = Column(Integer)   # 10
    apply_start  = Column(Date)      # 2026-08-01
    apply_end    = Column(Date)      # 2026-08-31
    notify_date  = Column(Date)      # 2026-08-31
    status       = Column(String, default="open")  # open | closed | notified
    created_at   = Column(DateTime, default=datetime.now)
```

회차 산출 규칙은 **대상월 2개월 전의 1일 ~ 말일**이다. 통보일은 접수 마감일과 같다. 매월 1일에 스케줄러가 `현재월 + 2` 회차를 자동 생성한다.

### 3-4. 기간 겹침 판정

골프의 슬롯 겹침 로직과 동일한 패턴을 쓴다. 체크아웃 날짜는 배타적이므로 연속 예약이 서로 충돌하지 않는다.

```python
# a와 b가 겹친다
a.start_date < b.end_date and a.end_date > b.start_date
```

즉 `8/1~8/3`(2박)과 `8/3~8/5`(2박)는 **겹치지 않는다**. 8/3에 한 팀이 퇴실하고 다른 팀이 입실한다.

별장 1채는 한 시점에 한 팀이 독점한다고 가정한다. `capacity`(20명)는 인원 상한 검증에만 쓴다.

### 3-5. 연박 상한 판정

7·8월은 최대 2박3일, 나머지 달은 제한이 없다. 판정 기준에 애매한 지점이 있어 아래처럼 정한다.

> **판정 규칙: 이용 기간이 성수기(7·8월) 날짜를 하루라도 포함하면 2박 제한을 적용한다.**
>
> 체크인 날짜의 월만 보면 `6/30 체크인 ~ 7/3 체크아웃`(3박)이 제한을 빠져나간다. 7월을 이틀 쓰면서 성수기 제한을 회피하는 셈이라 규칙의 취지(성수기 혼잡 완화)에 맞지 않는다. 따라서 **기간이 성수기와 겹치는지**로 판정한다.

| 예시 | 성수기 포함 | 판정 |
|---|---|---|
| `7/10 ~ 7/12` (2박) | O | 허용 |
| `7/10 ~ 7/13` (3박) | O | **거부** |
| `6/30 ~ 7/3` (3박) | O (7/1~7/2) | **거부** |
| `6/25 ~ 6/28` (3박) | X | 허용 |
| `9/1 ~ 9/8` (7박) | X | 허용 |

### 3-6. 월말 걸침 연박

정규예약은 회차의 **대상월**에 속한 예약을 받는다. `10/31 체크인 ~ 11/2 체크아웃`처럼 월을 넘는 경우가 생긴다.

> **규칙: 체크인 날짜가 대상월에 속하면 신청 가능하다.** 다음 달 회차에서는 그 기간이 이미 점유된 것으로 달력에 표시된다.

체크인 기준으로 회차를 판정하는 게 사용자 직관에 맞고(예약은 들어가는 날로 인식한다), 겹침 판정이 회차와 무관하게 동작하므로 이중 배정도 발생하지 않는다.

---

## 4. API 설계

### 사용자 API — `backend/app/routers/villa.py` (`/api/villa`)

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/facilities` | 별장 목록 + 설정(정원, 기본 입퇴실 시간, 안내문) |
| GET | `/calendar?facility_id=&year=&month=` | 달력용 예약 현황. 확정/신청중/내신청 구분 |
| GET | `/current-round` | 현재 접수중인 회차 정보 (대상월, 마감일) |
| POST | `/apply` | 신청 생성. 정규(기간 내) 또는 선착순 |
| GET | `/my` | 내 신청·확정 목록 |
| POST | `/cancel/{id}` | **`applied` 상태만** 즉시 취소 |
| POST | `/cancel-request/{id}` | **`confirmed` 상태** 취소 요청. 관리자 승인 대기 |
| GET | `/{id}/extra` | 추가입력 조회 (본인만) |
| POST | `/{id}/extra` | 추가입력 저장 (본인만, 확정 상태만) |

### 관리자 API — 동일 파일의 admin 섹션 (`/api/villa/admin`)

골프가 `golf.py` 한 파일에 admin 섹션을 두는 패턴을 따른다.

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/admin/rounds` | 회차 목록 |
| POST | `/admin/rounds` | 회차 수동 생성·수정 (예외 상황 대응) |
| GET | `/admin/applications?round_id=` | 신청 목록. 겹치는 건끼리 그룹으로 묶어 반환 |
| POST | `/admin/confirm/{id}` | 확정. 겹치는 나머지 신청은 자동 `rejected` |
| POST | `/admin/notify/{round_id}` | 확정 결과 일괄 통보 (Slack + 메일) |
| GET | `/admin/cancel-requests` | 취소 요청 목록 (승인 대기) |
| POST | `/admin/cancel-approve/{id}` | 취소 승인 → `canceled`, 기간 재개방 |
| POST | `/admin/cancel-reject/{id}` | 취소 반려 → `confirmed` 복귀 |
| GET | `/admin/settings` / POST | 별장 설정(성수기 규칙, 기본 시간, 안내문) |

### SMTP 설정 API — `/api/admin/smtp`

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/admin/smtp` | 설정 조회. **비밀번호는 마스킹(`••••••`)해서 반환** |
| POST | `/api/admin/smtp` | 설정 저장. 비밀번호가 마스킹 값이면 기존 값 유지 |
| POST | `/api/admin/smtp/test` | 테스트 메일 발송 |

---

## 5. SMTP 비밀번호 암호화

### 저장 방식

`SystemSetting`의 `key='smtp_settings'`에 JSON으로 저장하되, 비밀번호 필드만 암호화한다.

```json
{
  "host": "smtp.bit.kr",
  "port": 587,
  "use_tls": true,
  "username": "noreply@bit.kr",
  "password_encrypted": "gAAAAABm...",
  "from_name": "BIT Wellness Center",
  "from_email": "noreply@bit.kr"
}
```

### 신규 모듈 — `backend/app/crypto_utils.py`

`cryptography`의 Fernet(대칭키)을 쓴다. **이 패키지는 이미 `requirements.txt`에 있어 추가 의존성이 0이다.**

암호화 키는 `.env`의 `SETTINGS_ENCRYPTION_KEY`(`Fernet.generate_key()` 결과)로 주입한다.

> **키 부재 시 동작은 `SECRET_KEY`와 다르게 설계한다.** `SECRET_KEY`는 없으면 앱이 기동을 거부하지만(Phase 3), SMTP는 부가 기능이므로 키가 없어도 앱은 떠야 한다. 따라서 모듈 import 시점이 아니라 **암복호화를 실제로 호출하는 시점에** 명확한 에러를 던진다. 메일 기능만 비활성되고 예약·헬스·골프는 정상 동작한다.

### 신규 모듈 — `backend/app/email_utils.py`

Python 표준 `smtplib` + `email.message`를 쓴다. 추가 의존성 없다. `slack_utils.py`와 같은 스타일로, 발송 실패가 예약 확정 트랜잭션을 깨지 않도록 예외를 삼키고 로그만 남긴다.

---

## 6. 확정 통보와 추가입력

### 통보 내용

Slack DM과 메일을 **동시에** 보낸다. Slack은 기존 `slack_utils.get_slack_user_id_by_email()`을 재사용한다.

```
🏡 [비트별장 예약 확정 안내]

청평별장 예약이 확정되었습니다.
• 이용 기간: 2026-10-10(금) ~ 2026-10-12(일) 2박
• 입실/퇴실: 15:00 / 11:00
• 사용 인원: 6명

아래 링크에서 차량 정보와 이용 구성을 입력해 주세요.
https://book.bit.kr/villa/extra/123
```

미선정자에게도 별도 문구로 통보한다.

### 추가입력 페이지 — `/villa/extra/[id]`

SSO 로그인 필수, 본인 예약만 접근한다(타인 접근 시 403). 입력 항목은 차량대수, 차량번호(대수만큼 동적 입력), 성인 수, 아동 수(15세 이하)다.

> **가정:** 성인+아동 합계가 신청 시 `participant_count`와 다르면 **경고만 표시하고 저장은 허용**한다. 실제 동행 인원은 확정 후 바뀌는 게 자연스러워서 강제 일치는 사용자를 막는다. 대신 관리자 목록에서 불일치 건에 표시를 남긴다.

---

## 7. 달력 UI/UX

직관성이 요구사항이라 아래 구조로 설계한다. **외부 캘린더 라이브러리를 쓰지 않는다** — 월 그리드는 순수 `Date` 연산 80줄 수준이고, 기존 코드도 날짜 라이브러리 없이 동작한다.

```
┌─────────────────────────────────────┐
│  [ 청평별장 ]  [  동비재  ]          │ ← 세그먼트 토글
├─────────────────────────────────────┤
│  📢 10월 예약 접수중 · 8/31 마감     │ ← 현재 회차 배너
├─────────────────────────────────────┤
│  일  월  화  수  목  금  토          │
│                                     │
│              1   2   3   4          │
│             ▓▓▓▓▓▓▓▓  ← 확정(연박 bar)
│             김직원 4명               │
│                                     │
│   5   6   7   8   9  10  11         │
│                 ░░░░░░░  ← 신청중   │
│                 3팀 경합             │
│                                     │
├─────────────────────────────────────┤
│  ▓ 확정   ░ 신청중   ● 내 신청       │ ← 범례
└─────────────────────────────────────┘
```

색 규칙은 골프 페이지의 우선순위 배지 톤과 맞춘다.

| 상태 | 표현 |
|---|---|
| 확정 | 진한 파란 bar + 예약자명·인원 |
| 신청중 | 연한 노란 bar + "N팀 경합" |
| 내 신청 | 초록 점 표시로 별도 강조 |
| 지난 날짜 | 회색 비활성, 탭 불가 |
| 접수 기간 외 | 확정된 날짜만 조회 가능, 신청 버튼 숨김 |

날짜를 탭하면 신청 모달이 열린다(체크인/체크아웃 날짜, 예상 입퇴실 시간, 인원). 하단에 "내 신청 현황" 섹션을 두어 상태 배지와 추가입력 필요 여부를 함께 보여준다.

---

## 8. 관리자 확정 화면 (중복 경합)

관리자가 무엇을 보고 판단할지가 이 화면의 핵심이다. 겹치는 신청을 하나의 그룹으로 묶어 나란히 보여준다.

```
┌── 2026-10-10 ~ 10-12 (3팀 경합) ─────────────────┐
│                                                  │
│  ① 김직원 / 개발팀    6명   신청 8/3  이력 0회   │ [확정]
│  ② 박사원 / 영업팀    4명   신청 8/7  이력 2회   │ [확정]
│  ③ 이과장 / 관리팀    8명   신청 8/12 이력 1회   │ [확정]
└──────────────────────────────────────────────────┘
```

표시 정보는 신청자·부서·인원·신청 순서(`created_at`)와 **과거 이용 이력 횟수**다. 이력을 넣는 이유는 공정성 판단의 근거가 필요하기 때문이다. 확정 버튼을 누르면 같은 그룹의 나머지는 자동 `rejected` 처리된다.

### 취소 요청 처리

같은 화면 상단에 승인 대기 중인 취소 요청을 배치한다. 방치되면 그 기간이 계속 묶여 있으므로 눈에 먼저 띄어야 한다.

```
┌── 취소 요청 2건 ────────────────────────────────┐
│  김직원 / 청평별장 10/10~10/12  요청 9/28       │
│  사유: 개인 사정                  [승인] [반려]  │
└─────────────────────────────────────────────────┘
```

취소 요청이 들어오면 관리자에게 Slack 알림을 보낸다. 승인·반려 결과는 신청자에게 Slack과 메일로 통보한다. 승인 시 해당 기간은 선착순 신청 대상으로 다시 열린다.

---

## 9. 메뉴 배치 변경

요청대로 [page.tsx:140](frontend/app/page.tsx:140)의 2열 그리드를 재구성한다.

**현재**
```
[ 스크린골프 ]  [ 이번 달 출석 ]
```

**변경 후**
```
[ 스크린골프 ]  [ 비트별장 ]
[      이번 달 헬스장 출석      ]
```

> **확인 필요:** 이번 달 출석 수치는 현재 [page.tsx:108](frontend/app/page.tsx:108)의 우측 상단 영역과 [page.tsx:156](frontend/app/page.tsx:156)의 카드에 **중복 표시**되고 있다. 재배치하면서 상단 중복을 제거할지, 둘 다 유지할지 확인이 필요하다.

관리자 페이지에는 `/admin/villa`(예약 관리)와 `/admin/smtp`(메일 설정) 카드를 [admin/page.tsx:137](frontend/app/admin/page.tsx:137) 옆에 추가한다.

---

## 10. 스케줄러 확장

[main.py:48](backend/app/main.py:48)의 `scheduled_jobs()`는 1분마다 돌고 있다. 여기에 날짜성 작업을 추가하되, 매분 실행되므로 **중복 실행 방지 플래그**가 필수다(`round.status`, `notified_confirmed`).

| 시점 | 작업 |
|---|---|
| 매월 1일 | `현재월 + 2` 회차 자동 생성 (이미 있으면 건너뜀) |
| 접수 마감 3일 전 | 관리자에게 "확정 필요" Slack 리마인더 |
| 접수 마감일 경과 | `round.status`를 `closed`로 전환, 신규 정규신청 차단 |
| 통보일 | 확정자에게 확정 통보, 미선정자에게 안내. `status`를 `notified`로 |

> **가정:** 통보일에 관리자가 아직 확정하지 않은 경합 건이 남아 있으면, 통보를 보류하고 관리자에게 경고 알림을 보낸다. 임의 자동 선정은 하지 않는다.

---

## 11. 선착순 예약 (통보 후)

회차가 `notified`로 전환되면 해당 대상월의 미확정 날짜는 접수 기간과 무관하게 신청 가능하다.

> **가정:** 선착순 신청은 **즉시 `confirmed`** 처리한다. "선착순"의 자연스러운 해석이고, 관리자 개입 없이 빈 날짜가 활용되게 하는 것이 요구사항의 취지로 보인다. 이미 확정된 기간과 겹치면 즉시 거부한다. 확정과 동시에 Slack·메일 통보와 추가입력 링크를 보낸다.

이 가정이 다르다면(선착순도 관리자 확정 필요) Phase 7에서 조정하면 되고, 앞 단계 설계에는 영향이 없다.

---

## 12. 구현 단계

| Phase | 내용 | 검증 |
|---|---|---|
| 1 | 스키마 2개 추가, 마이그레이션 스크립트, 별장 2개 시드 | 테이블 생성·시드 확인 |
| 2 | 신청/조회 API, 회차 로직, 겹침 판정, 성수기 연박 제한 | pytest — 겹침 경계, 중복 허용, 기간 외 거부, 2박 제한 |
| 3 | 사용자 달력 UI + 메뉴 재배치 | 로컬 화면 확인 |
| 4 | 관리자 확정 UI (경합 그룹) + 취소 승인 | pytest — 확정 시 나머지 rejected, 취소 승인 시 기간 재개방 |
| 5 | SMTP 설정 + 암호화 + 테스트 발송 | pytest — 암복호화 왕복, 마스킹 |
| 6 | 확정 통보(Slack+메일) + 추가입력 페이지 | pytest — 본인 외 403 |
| 7 | 선착순 예약 + 스케줄러 자동화 | pytest — 즉시 확정, 중복 실행 방지 |
| 8 | 통합 검증 + 배포 | 실 PostgreSQL + 원격 스모크 |

기존 `backend/tests/` 하네스(93개 통과 중)를 그대로 재사용한다. `conftest.py`의 `facilities` 픽스처에 villa 2개를 추가한다.

---

## 13. 남은 열린 항목

기본안을 정해둔 것들이다. 이견이 없으면 그대로 진행한다.

1. **이번 달 출석 중복 표시** — 상단 영역과 카드 중 하나를 제거할지 (9절)
2. **선착순 즉시 확정** — 기본안은 즉시 확정 (11절)
3. **성인+아동 합계 불일치** — 기본안은 경고만 (6절)
4. **통보일 미확정 건 처리** — 기본안은 통보 보류 + 관리자 경고 (10절)
5. **성수기 연박 판정 기준** — 기본안은 "기간이 7·8월을 하루라도 포함하면 2박 제한" (3-5절). 체크인 월 기준으로 완화할 수도 있다
6. **취소 사유 입력** — 취소 요청 시 사유를 필수로 받을지. 기본안은 선택 입력

### 해결된 항목

- ~~확정 후 취소 정책~~ → 관리자 승인 필요로 확정
- ~~인원 상한~~ → 두 별장 모두 20명
- ~~연박 상한~~ → 7·8월 2박3일, 그 외 제한 없음

---

## 14. 이 기획에 포함하지 않은 것

- **결제·정산** — 요구사항에 없다
- **별장 QR 입퇴실** — 헬스·골프와 달리 `AccessLog`를 쓰지 않는다. 필요해지면 3-1절의 `admin.py` 분기를 먼저 고쳐야 한다
- **디자인 시스템 도입** — 직전 대화의 shadcn/ui 검토는 별건이다. 이 기능은 기존 Tailwind 커스텀 톤으로 구현한다
- **월 단위 이용 횟수 제한** — 공정성 규칙(예: 연 2회 제한)은 요구사항에 없다. 필요하면 별건
