# BIT Health 개선 계획안

작성일: 2026-07-27
전제: **기존 작동에 문제가 없어야 한다.** 즉 현재 서비스 중인 동작(SSO 로그인 세션, 골프 예약/선점 규칙, 입퇴실, Slack 알림, 관리자 권한)이 개선 전후로 동일해야 한다.

---

## 0. 설계 원칙

1. **먼저 안전망, 다음 수정.** 회귀 테스트가 없는 상태에서 인증·시간 로직을 건드리는 것은 위험하다. Phase 0에서 현재 동작을 고정하는 특성화 테스트(characterization test)를 먼저 작성한다.
2. **세션을 끊지 않는다.** JWT 만료가 1년이고 토큰이 localStorage에 있어, 서명 키를 그냥 교체하면 전 직원이 강제 로그아웃된다. 이중 키 검증으로 무중단 전환한다.
3. **관리자 권한을 잃지 않는다.** 권한 판정 로직을 바꿀 때 DB의 기존 `role='admin'` 값을 항상 우선한다. 어떤 단계에서도 관리자 접근이 끊기지 않는다.
4. **데이터 백필은 하지 않는다.** 과거 행의 기준이 섞여 있어 일괄 보정 시 어느 행이 어느 기준인지 판별할 수 없다. 스키마·비교 로직만 정합화한다.
5. **요청 범위만 건드린다.** 미사용(no-show) 패널티 주석 코드처럼 의도적 비즈니스 결정은 그대로 둔다.

---

## 1. 사전 조사 결과 (계획의 근거)

| 확인 항목 | 결과 | 계획에 미치는 영향 |
|---|---|---|
| `/login` 페이지의 레거시 로그인 폼 | **없음.** SSO 버튼 단독 | `/api/auth/login` 수정의 사용자 영향 0 |
| `lib/auth.ts:login()` 호출처 | **없음** (죽은 코드) | 동일 |
| `/api/auth/login` 실제 소비자 | `backend/test_login.py`, `backend/debug_remote_access.py` | `admin/000000` 로그인은 계속 되게 유지 |
| `AccessLog.check_in_time` 실제 저장값 | gym·golf 모두 `datetime.now()` 명시 전달 → KST naive | `default=utcnow`는 미발화. 데이터 영향 없이 선언만 정정 가능 |
| 엑셀 업로드 UI | **없음** (`/api/users/upload`만 존재) | 이 계획에서 건드리지 않음 |
| `get_db` 정의 위치 | `database.py`와 `auth.py`에 **중복 정의**. 라우터가 서로 다른 쪽을 import | 테스트에서 `dependency_overrides`를 **양쪽 모두** 등록해야 함 |
| 모델의 PostgreSQL 전용 타입 | 없음 (JSONB/ARRAY 미사용) | 테스트를 SQLite in-memory로 구성 가능 |

---

## 2. Phase 0 — 회귀 안전망 구축 (선행 필수)

이 계획 전체의 "기존 작동 무영향"을 검증하는 수단이다. 여기서 만든 테스트가 이후 모든 Phase의 통과 기준이 된다.

### 작업
- `backend/requirements-dev.txt` 추가 — `pytest`, `httpx`
- `backend/tests/conftest.py` — SQLite in-memory 엔진 + `database.get_db`와 `auth.get_db` **양쪽** `dependency_overrides` 등록, Facility 시드(Gym/ScreenGolf) 픽스처, 인증된 클라이언트 픽스처
- `backend/tests/test_golf_priority.py` — 선점 규칙 9조합 매트릭스(내 우선순위 1~3 × 기존 1~3), 3시간 규칙 경계, 다중 슬롯 2-패스(일부 거부 시 **아무 예약도 취소되지 않음**), 본인 중복 예약 차단
- `backend/tests/test_golf_slots.py` — 평일 2시간 블록, 주말 1시간 단위, 공휴일이 주말 규칙으로 처리되는지
- `backend/tests/test_gym.py` — 혼잡도 경계값(정원의 50%, 80%), 입퇴실 토글
- `backend/tests/test_auth.py` — SSO 신규/기존 사용자 처리(외부 HTTP는 mock), 토큰 발급·검증
- `backend/tests/test_dashboard.py` — 월간 카운트, 오늘 예약 여부
- `backend/tests/test_auth_bypass.py` — **현재 취약점을 명시적으로 고정.** `{"name": "<SSO사용자>"}`만 보내면 200이 나오는 현재 동작을 테스트로 박아두고, Phase 1에서 401 기대로 뒤집는다.

### 검증
`cd backend && pytest` 전체 통과. 이 시점의 통과 결과가 기준선(baseline)이다.

### 커밋
`test: 기존 동작 고정을 위한 회귀 테스트 추가`

---

## 3. Phase 1 — 인증 우회 차단 🔴

### 문제
`schemas.LoginRequest.birth_date`가 `Optional = None`이고 `crud.get_user_by_name_and_birth`의 `birth_date == None`이 SQL `IS NULL`로 컴파일된다. SSO 사용자는 `birth_date`가 NULL이므로 `{"name": "이영배"}`만으로 관리자 토큰이 발급된다.

### 조치
- `crud.get_user_by_name_and_birth`에 `models.User.birth_date.isnot(None)` 조건 추가 — SSO 계정이 이 경로로 절대 매칭되지 않게 한다.
- `schemas.LoginRequest.birth_date`를 필수(`str`)로 변경하고, 라우터에서 6자리 숫자 형식을 검증한다.

### 기존 작동 영향
없음. UI에 이 경로가 없고, `admin/000000`(birth_date 보유)은 계속 로그인된다.

### 검증
- `test_auth_bypass.py`를 401 기대로 뒤집고 통과
- `admin/000000` 로그인 200 유지
- `pytest` 전체 통과

### 커밋
`fix: 생년월일 NULL 매칭을 통한 인증 우회 차단`

---

## 4. Phase 2 — 배포 자격증명 분리 🔴

### 문제
`deploy.py:9`에 서버 계정 비밀번호가 평문으로, git에 추적된 상태로 존재한다.

### 조치
- `HOST` / `USERNAME` / `PASSWORD`를 `.env`의 `DEPLOY_HOST` / `DEPLOY_USER` / `DEPLOY_PASSWORD`에서 읽는다. `.env`는 이미 `.gitignore` 대상이고, `deploy.py`가 tar에 포함해 서버로 전송하므로 기존 배포 흐름이 유지된다.
- 의존성을 늘리지 않기 위해 `.env`는 6줄짜리 직접 파싱으로 읽는다(로컬 전용 스크립트).
- 값이 없으면 배포를 시작하지 않고 무엇을 채워야 하는지 안내하며 종료한다.

### 사용자 조치 필요 (코드로 해결 불가)
- **서버 계정 비밀번호 회전.** 평문 값이 이미 커밋 히스토리에 남아 있으므로 코드 수정만으로는 노출이 해소되지 않는다.
- git 히스토리 재작성은 **권하지 않는다.** 원격 저장소와 다른 클론을 깨뜨리는 대가가 크고, 회전이 더 확실한 해결이다.
- (후속 선택지) 비밀번호 대신 SSH 키 인증으로 전환.

### 검증
`.env`에 값을 채우고 `python deploy.py` 정상 완료. 값을 비우면 명확한 메시지와 함께 실패.

### 커밋
`refactor: 배포 스크립트 자격증명을 .env로 분리`

---

## 5. Phase 3 — JWT SECRET_KEY 외부화 (무중단) 🟡

### 문제
`auth.py:11`의 `os.getenv("SECRET_KEY", "bit_health_secret_key_2026")`에서, 운영 compose가 `SECRET_KEY`를 주입하지 않아 소스에 적힌 하드코딩 키로 실제 토큰이 서명되고 있다.

### 핵심 리스크
키를 그냥 교체하면 유효기간 1년의 기존 토큰이 전부 무효화되어 **전 직원이 강제 로그아웃**된다. 이는 "기존 작동에 문제 없도록"에 정면으로 위배된다.

### 조치 (이중 키 전환)
- 발급은 **항상 새 `SECRET_KEY`**로 한다.
- 검증은 새 키로 시도하고, 실패하면 `LEGACY_SECRET_KEY`(=현재 하드코딩 값)로 한 번 더 시도한다. 둘 다 실패하면 401.
- `SECRET_KEY`를 `.env`에 넣고 `docker-compose.yml`·`deploy_docker_compose.yml`의 backend `environment`에 추가한다.
- 전환 기간(2~4주, 기존 토큰이 자연 교체될 기간) 경과 후 **레거시 폴백 제거를 별도 커밋으로** 진행한다. 이 제거 시점에만 잔여 구토큰 보유자가 재로그인하며, SSO 1클릭이라 영향이 작다.

### 범위에서 분리
토큰 만료 1년 → 단기 축소는 재로그인을 유발하는 정책 결정이므로 이 계획에 포함하지 않는다. 별건으로 판단이 필요하다.

### 검증
- 레거시 키로 서명한 토큰으로 `/api/users/me` 200
- 새 키로 서명한 토큰으로 `/api/users/me` 200
- 무관한 키로 서명한 토큰 401
- 배포 후 기존 브라우저 세션이 로그아웃되지 않는지 실제 확인

### 커밋
`fix: JWT 서명 키 외부화 및 무중단 전환용 레거시 키 검증 추가`

---

## 6. Phase 4 — 관리자 판정 하드코딩 제거 🟡

### 문제
`routers/auth.py:84`의 `role = "admin" if name == "이영배" else "user"`. 동명이인이 SSO 로그인하면 관리자 권한을 얻는다.

### 조치
- `ADMIN_EMAILS` 환경변수(콤마 구분)를 도입한다. 신규 SSO 사용자 생성 시 이메일이 목록에 있으면 `admin`, 아니면 `user`.
- 기존 사용자의 이름 기반 자동 승격 분기(`elif user.name == "이영배"`)를 이메일 기준으로 교체한다.
- **안전장치:** DB에 이미 `role='admin'`인 사용자는 DB 값을 그대로 유지한다. 이 로직은 승격만 하고 강등하지 않으므로, 설정이 잘못돼도 관리자 접근을 잃지 않는다.

### 선행 확인 필요
운영 DB에서 현재 관리자 계정의 `email` 컬럼이 실제로 채워져 있는지 확인한다(SSO payload에 email이 없으면 NULL일 수 있다). 비어 있다면 이메일 대신 SSO `sub` 기준(`ADMIN_SUBS`)으로 구성한다. `backend/check_users.py`로 확인 가능하다.

### 검증
- 관리자 재로그인 후 `role='admin'` 유지
- 목록에 없는 이름/이메일은 `user` 부여 (동명이인 시나리오 테스트)
- `/api/users/{id}/role`을 통한 수동 권한 부여 경로 정상 동작

### 커밋
`fix: SSO 관리자 판정을 이름 하드코딩에서 환경변수 기반으로 변경`

---

## 7. Phase 5 — 타임존 정합 🟡

### 문제
`models.py`의 기본값은 `datetime.utcnow`, 실제 코드는 `datetime.now()`(컨테이너 `TZ=Asia/Seoul`), `users.py:148`의 대시보드는 tz-aware KST를 naive 컬럼과 비교한다.

### 조사로 좁혀진 실제 범위
`AccessLog.check_in_time`의 `default=utcnow`는 gym·golf 양쪽이 값을 명시 전달하므로 **발화하지 않는다.** 따라서 저장 데이터는 이미 KST 일관이고, 문제는 (a) 선언과 실제의 불일치, (b) 대시보드의 aware/naive 혼용 비교 두 가지다.

### 조치
- `models.py`의 `default=datetime.utcnow`를 KST naive와 일치하도록 정정한다. `AccessLog`는 미발화라 영향 0, `User.created_at`은 신규 행부터 KST 기준이 된다.
- `users.py:148-162`의 tz-aware KST 계산을 naive `datetime.now()` 기준으로 변경해 naive 컬럼과 정합을 맞춘다.

### 백필하지 않는 이유
`User.created_at`의 과거 행은 UTC 기준이라 9시간 이르게 표시된다. 다만 이 값은 표시 전용이고, 과거 행 중 어느 것이 UTC이고 어느 것이 KST인지 판별할 근거가 없어 일괄 보정은 새 오류를 만든다. 리스크가 이득보다 크다.

### 검증
KST 자정 경계(예: 월초 00:00 직후, 월말 23:59)에서 월간 카운트와 "오늘 예약 여부"가 정확한지 경계 테스트로 확인한다.

### 커밋
`fix: 타임존 기준을 KST naive로 통일`

---

## 8. Phase 6 — 잔여 정리 🟢

### 조치
- `main.py:37`의 개발 중 메모(`# Now golf is in __init__? Check first.`) 삭제
- `admin.py:3-4`의 중복 import 정리
- `lib/api.ts:1`의 폴백을 로컬 개발용 `http://localhost:8002`로 변경. 운영은 compose가 build args와 runtime env 양쪽으로 `https://book.bit.kr`를 주입하므로 영향이 없고, README 6-3) 원칙도 유지된다.

### 그대로 두는 것
- `golf.py:220`의 미사용 패널티 주석 코드 — 의도적 비즈니스 결정
- 다음 죽은 코드는 **보고만 하고 삭제는 승인 후** 진행한다.
  - `lib/auth.ts:login()` — 미참조
  - `/api/users/upload` — 대응 UI 없음
  - `/api/admin/dashboard/golf-reservations` — 빈 배열만 반환하는 플레이스홀더
  - `/api/admin/golf/available-times` — 미구현 스텁

### 커밋
`chore: 개발 중 메모 및 중복 import 정리`

---

## 9. Phase 7 — 통합 검증 및 배포

1. `cd backend && pytest` 전체 통과
2. `docker compose up -d --build`로 로컬 기동, 다음 플로우 수동 확인
   - SSO 로그인 → 메인 대시보드 → 헬스 인원 표시
   - `/access` 입실 → 퇴실
   - `/golf` 예약 생성 → 선점 시나리오 → 취소
   - `/admin` 통계, 사용자 권한 변경
3. `python deploy.py`
4. 원격 스모크 — `https://book.bit.kr` 로그인, **기존 브라우저 세션 유지 확인**(Phase 3의 핵심 검증), 예약 1건, Slack 알림 수신
5. `fetch_remote_logs.py`로 스케줄러 정상 동작 확인

---

## 10. 순서와 근거

| 순서 | Phase | 근거 |
|---|---|---|
| 1 | 0. 회귀 테스트 | 이후 전 단계의 검증 수단. 없으면 무영향을 증명할 수 없다 |
| 2 | 1. 인증 우회 | 🔴 권한 탈취 경로. 사용자 영향 0이라 즉시 가능 |
| 3 | 2. 배포 자격증명 | 🔴 노출된 비밀. 런타임 무관이라 독립 실행 가능 |
| 4 | 3. SECRET_KEY | 🟡 세션에 영향. 이중 키 설계가 필요해 신중히 |
| 5 | 4. 관리자 판정 | 🟡 권한에 영향. Phase 3 이후 토큰 체계가 안정된 뒤 |
| 6 | 5. 타임존 | 🟡 데이터 정합. 통계 정확도 |
| 7 | 6. 정리 | 🟢 위험 없음 |

---

## 11. 리스크와 롤백

| 리스크 | 완화 | 롤백 |
|---|---|---|
| 전 직원 강제 로그아웃 (Phase 3) | 이중 키 검증으로 구토큰 계속 수용 | `.env`의 `SECRET_KEY`를 되돌리면 즉시 복구. 레거시 폴백 덕분에 무중단 |
| 관리자 접근 상실 (Phase 4) | DB `role` 우선, 승격만 하고 강등 없음 | `git revert` + DB에서 `role='admin'` 직접 세팅 |
| 통계 수치 변동 (Phase 5) | 백필 없음, 비교 로직만 정합화 | `git revert` |
| SQLite 테스트가 PostgreSQL 동작과 다름 | 모델에 PG 전용 타입 없음을 확인. 최종 검증은 Phase 7에서 실제 PG로 | 해당 없음 |
| 배포 스크립트 동작 불가 (Phase 2) | 값 누락 시 배포 시작 전에 실패 | `git revert` |

각 Phase는 단일 커밋이므로 개별 `git revert`가 가능하다.

---

## 12. 이 계획에 포함하지 않은 것

- **JWT 만료 1년 단축** — 재로그인을 유발하는 정책 결정. 별도 판단 필요
- **Alembic 등 마이그레이션 도구 도입** — 현재 `create_all` + 수동 스크립트로 운영 중. 개선 가치는 있으나 요청 범위 밖의 구조 변경
- **죽은 엔드포인트 삭제** — 보고만 하고 승인 후 별건 처리
- **git 히스토리 재작성** — 비밀번호 회전이 더 안전한 해결
- **미사용 패널티 재활성화** — 의도적으로 중단된 비즈니스 로직
