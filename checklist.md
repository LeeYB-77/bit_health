# BIT Health 개선 체크리스트

상세 근거는 [improvement-plan.md](improvement-plan.md), 작업 중 판단은 [context-notes.md](context-notes.md) 참조.
표기: 🔴 즉시 / 🟡 신중 / 🟢 안전

**진행 상태: Phase 0~6 완료 및 커밋. Phase 7 로컬 검증 완료, 원격 배포는 미실행(사용자 승인 대기).**

---

## Phase 0 — 회귀 안전망 (선행 필수) ✅ 완료

- [x] `backend/requirements-dev.txt` 추가 (`pytest`, `httpx`)
- [x] `backend/tests/conftest.py` — SQLite in-memory 엔진
- [x] `conftest.py` — `database.get_db`와 `auth.get_db` **양쪽** `dependency_overrides` 등록
- [x] `conftest.py` — Facility 시드(Gym 정원 15 / ScreenGolf 정원 1) 픽스처
- [x] `conftest.py` — 인증된 클라이언트 픽스처(일반/관리자)
- [x] `test_golf_priority.py` — 선점 9조합 매트릭스 (1~3 × 1~3)
- [x] `test_golf_priority.py` — 3시간 규칙 경계
- [x] `test_golf_priority.py` — 다중 슬롯 2-패스: 일부 거부 시 **아무 예약도 취소되지 않음**
- [x] `test_golf_priority.py` — 본인 중복 예약 차단
- [x] `test_golf_priority.py` — 2인 이상 예약 시 동반자 필수
- [x] `test_golf_slots.py` — 평일 2시간 블록 / 주말 1시간 단위 / 공휴일 처리
- [x] `test_gym.py` — 혼잡도 경계값 / 입퇴실 토글
- [x] `test_auth.py` — SSO 신규·기존 사용자 (외부 HTTP mock)
- [x] `test_dashboard.py` — 월간 카운트, 오늘 예약 여부
- [x] `test_admin.py` — 관리자 통계·현재 이용자·이용 이력 (계획에 없었으나 커버리지 보강을 위해 추가)
- [x] `test_auth_bypass.py` — 당시 취약점을 200 기대로 고정
- [x] ✅ 검증: `pytest` 79개 전체 통과 → 기준선 확정
- [x] 📦 커밋 `0353c0e`: `test: 기존 동작 고정을 위한 회귀 테스트 추가`

## Phase 1 — 인증 우회 차단 🔴 완료

- [x] `crud.get_user_by_name_and_birth`에 `User.birth_date.isnot(None)` 추가
- [x] `schemas.LoginRequest.birth_date`를 필수(`str`)로 변경
- [x] `users.create_user`의 형식 검증을 중복 검사보다 앞으로 이동 (birth_date=None일 때 500나던 경로 정리)
- [x] `test_auth_bypass.py`를 401/422 기대로 뒤집고 보강
- [x] ✅ 검증: `{"name": "..."}` 단독 요청 → 422 (스키마 단계 차단)
- [x] ✅ 검증: `admin`/`000000` 로그인 → 200 유지 (Phase 7 실컨테이너에서도 재확인)
- [x] ✅ 검증: `pytest` 84개 전체 통과
- [x] 📦 커밋 `53cc8e7`
- 📌 **추가 확인(운영 DB 조회 결과):** SSO 사용자 43명 전원 `birth_date` NULL이었음. 즉 수정 전에는 이론이 아니라 실제로 이름만으로 관리자 계정(id=144, 147) 로그인이 가능한 상태였음.

## Phase 2 — 배포 자격증명 분리 🔴 완료 (계획보다 범위 확대)

- [x] `.env`에 `DEPLOY_HOST`/`DEPLOY_USER`/`DEPLOY_PASSWORD`/`DEPLOY_PORT`/`REMOTE_DATABASE_URL` 추가
- [x] `remote_config.py` 신규 — `.env` 직접 파싱, 누락 시 종료코드 1로 중단
- [x] **`deploy.py` 외 7개 스크립트에서 동일 비밀번호 하드코딩 발견** — 전부 처리:
  `check_remote_status.py`, `cleanup_remote_db.py`, `debug_remote.py`, `fetch_remote_logs.py`, `init_remote_db.py`, `migrate_golf_priority.py`, `migrate_slack_notified.py`
- [x] `migrate_remote_db.py`, `migrate_sso_db.py`의 DB 접속 문자열도 `REMOTE_DATABASE_URL`로 이동
- [x] ✅ 검증: `.env` 채운 상태로 `remote_config` import 정상, 값 마스킹 출력 확인
- [x] ✅ 검증: `.env` 없는 디렉터리에서 실행 → 안내 메시지 + 종료코드 1
- [x] 📦 커밋 `17404dc`
- [ ] ⚠️ **사용자 조치 필요: 서버 계정 비밀번호(`bitcom1983!`) 회전.** 8개 파일 전부에서 코드상 제거했지만 git 히스토리에는 평문 값이 남아 있음. 코드 수정만으로는 해소되지 않음.

## Phase 3 — SECRET_KEY 외부화 (무중단) 🟡 완료

- [x] `.env`에 신규 `SECRET_KEY`(48바이트 랜덤) 및 `LEGACY_SECRET_KEY=bit_health_secret_key_2026` 추가
- [x] `auth.py` — 발급은 항상 신규 키, 검증은 신규 → 실패 시 레거시 순으로 폴백
- [x] `auth.py` — 하드코딩 기본값 제거, 미설정 시 `RuntimeError`로 기동 중단
- [x] `docker-compose.yml` / `deploy_docker_compose.yml`에 `SECRET_KEY`, `LEGACY_SECRET_KEY` 주입
- [x] `test_auth.py` — 레거시 키 토큰 수용 / 신규 토큰은 레거시 키로 검증 불가 / 만료된 레거시 토큰 거부 / 폴백 제거 후 구토큰 거부
- [x] ✅ 검증: `pytest` 88개 통과
- [x] ✅ 검증(Phase 7, 실 컨테이너): 레거시 키 서명 토큰 → 200, 무관한 키 서명 토큰 → 401
- [x] 📦 커밋 `cf85bd9`
- [ ] 🗓 **후속 작업 (2~4주 후, 별도 커밋):** `.env`의 `LEGACY_SECRET_KEY`와 `auth.py`의 폴백 로직 제거. 잊으면 히스토리에 남은 구 키로 위조한 토큰이 계속 통과함.

## Phase 4 — 관리자 판정 하드코딩 제거 🟡 완료

- [x] 🔍 **선행 확인 완료:** 운영 DB 직접 조회(읽기 전용) — SSO 사용자 43명 전원 `email` 채워져 있음 확인. `ADMIN_SUBS` 대안 불필요.
- [x] `.env`에 `ADMIN_EMAILS=lyb77@bit.kr,hjcho@bit.kr` 추가 (운영 관리자 2명의 실제 이메일)
- [x] `routers/auth.py` — 이름 하드코딩을 `ADMIN_EMAILS` 조회(대소문자 무시)로 교체
- [x] 승격만 하고 강등하지 않음 — 신규/기존 사용자 양쪽 분기에 적용
- [x] `docker-compose.yml` / `deploy_docker_compose.yml`에 `ADMIN_EMAILS` 주입
- [x] `test_auth.py` — 목록 이메일→admin, 대소문자 무시, 동명이인 차단, email 없음→user, 승격, 강등 안 됨 6종
- [x] ✅ 검증: `pytest` 93개 통과
- [x] 📦 커밋 `8671950`

## Phase 5 — 타임존 정합 🟡 완료

- [x] `models.py` — `User.created_at` 기본값을 KST naive(`datetime.now`)로 정정
- [x] `models.py` — `AccessLog.check_in_time` 기본값 동일 정정 (미발화 확인됨, 선언 정합용)
- [x] `users.py` 대시보드 — tz-aware KST → naive `datetime.now()` 기준으로 통일, 미사용 `timezone` import 제거
- [x] ❌ 백필하지 않음 (과거 행 기준 판별 불가)
- [x] ✅ 검증: `pytest` 93개 통과 (SQLite — tzinfo 무시하므로 회귀만 확인)
- [x] ✅ **검증(Phase 7, 실 PostgreSQL):** 오늘 헬스 입실 → `monthly_count: 1` 정상 반영. 오늘 골프 예약 → `has_today_reservation: true` 정상 반영. `created_at`이 KST 벽시계 시각과 일치.
- [x] 📦 커밋 `efbfa47`

## Phase 6 — 잔여 정리 🟢 완료

- [x] `main.py` 개발 중 메모(`# Now golf is in __init__?...`) 삭제
- [x] `admin.py` 중복 import 정리
- [x] `lib/api.ts` 폴백을 `http://localhost:8002`로 변경, `tsc --noEmit` 통과 확인
- [x] ❌ `golf.py`의 미사용 패널티 주석은 그대로 둠 (의도적 비즈니스 결정)
- [x] 📦 커밋 `381e911`
- 💬 **보고만 함, 삭제는 미실행 (승인 필요):** `lib/auth.ts:login()`(미참조), `/api/users/upload`(대응 UI 없음), `/api/admin/dashboard/golf-reservations`(빈 배열 스텁), `/api/admin/golf/available-times`(미구현 스텁)

## Phase 7 — 통합 검증 및 배포

- [x] `cd backend && pytest` 93개 전체 통과
- [x] Docker Desktop 기동 → `docker compose up -d --build` 로컬 스택 기동 (실제 PostgreSQL 15)
- [x] `initial_data.py`로 admin/Gym/ScreenGolf 시드
- [x] API 스모크: 레거시 로그인(admin/000000) 정상, 우회 시도 422 거부
- [x] API 스모크: 헬스 입실 → 대시보드 월간 카운트 반영 → 헬스 상태 조회 → 퇴실
- [x] API 스모크: 오늘 골프 슬롯 조회 → 예약 생성 → 대시보드 오늘예약 반영 → 취소
- [x] API 스모크: 레거시 키 토큰 수용, 무관한 키 토큰 401 거부
- [x] API 스모크: 관리자 대시보드 통계 조회
- [x] 컨테이너 내 환경변수 주입 확인 (SECRET_KEY, LEGACY_SECRET_KEY, ADMIN_EMAILS, SLACK_BOT_TOKEN)
- [x] `docker compose down`으로 로컬 스택 정리
- [x] README에 환경변수 표, 테스트 실행법 추가 (6·7번 항목)
- [ ] ⛔ **미실행 (승인 필요): 실제 SSO 로그인 플로우.** drive.bit.kr 실서버 연동이라 로컬에서 재현 불가. 원격 배포 후 사람이 직접 확인 필요.
- [ ] ⛔ **미실행 (승인 필요): `python deploy.py` 원격 배포.** SSH로 운영 서버(59.10.164.2)에 접속해 컨테이너를 재기동하는 외향적 행동이라 별도 확인 후 진행.
- [ ] 원격 배포 후: `https://book.bit.kr` 로그인, **기존 브라우저 세션 유지 확인**(Phase 3 핵심 검증)
- [ ] 원격 배포 후: 예약 1건 생성, Slack 알림 수신
- [ ] 원격 배포 후: `fetch_remote_logs.py`로 스케줄러 정상 동작 확인

---

## 남은 것 (사용자 확인/조치 필요)

1. **서버 계정 비밀번호 회전** (Phase 2) — 히스토리에 평문 잔존
2. **원격 배포 실행 여부 확인** (Phase 7) — `python deploy.py` 실행 승인
3. **레거시 SECRET_KEY 폴백 제거 일정** (Phase 3) — 2~4주 후 후속 커밋으로 예정
