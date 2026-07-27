# BIT Health 개선 체크리스트

상세 근거는 [improvement-plan.md](improvement-plan.md) 참조.
표기: 🔴 즉시 / 🟡 신중 / 🟢 안전

---

## Phase 0 — 회귀 안전망 (선행 필수)

- [ ] `backend/requirements-dev.txt` 추가 (`pytest`, `httpx`)
- [ ] `backend/tests/conftest.py` — SQLite in-memory 엔진
- [ ] `conftest.py` — `database.get_db`와 `auth.get_db` **양쪽** `dependency_overrides` 등록
- [ ] `conftest.py` — Facility 시드(Gym 정원 15 / ScreenGolf 정원 1) 픽스처
- [ ] `conftest.py` — 인증된 클라이언트 픽스처(일반/관리자)
- [ ] `test_golf_priority.py` — 선점 9조합 매트릭스 (1~3 × 1~3)
- [ ] `test_golf_priority.py` — 3시간 규칙 경계 (2h59m 거부 / 3h01m 허용)
- [ ] `test_golf_priority.py` — 다중 슬롯 2-패스: 일부 거부 시 **아무 예약도 취소되지 않음**
- [ ] `test_golf_priority.py` — 본인 중복 예약 차단
- [ ] `test_golf_priority.py` — 2인 이상 예약 시 동반자 필수
- [ ] `test_golf_slots.py` — 평일 2시간 블록 생성
- [ ] `test_golf_slots.py` — 주말 1시간 단위 생성
- [ ] `test_golf_slots.py` — 공휴일이 주말 규칙으로 처리
- [ ] `test_gym.py` — 혼잡도 경계값 (정원 50% → medium, 80% → high)
- [ ] `test_gym.py` — 입퇴실 토글
- [ ] `test_auth.py` — SSO 신규 사용자 생성 (외부 HTTP mock)
- [ ] `test_auth.py` — SSO 기존 사용자 재로그인
- [ ] `test_dashboard.py` — 월간 카운트, 오늘 예약 여부
- [ ] `test_auth_bypass.py` — **현재 취약점을 200 기대로 고정** (Phase 1에서 뒤집을 대상)
- [ ] ✅ 검증: `cd backend && pytest` 전체 통과 → 이 결과가 기준선
- [ ] 📦 커밋: `test: 기존 동작 고정을 위한 회귀 테스트 추가`

## Phase 1 — 인증 우회 차단 🔴

- [ ] `crud.get_user_by_name_and_birth`에 `User.birth_date.isnot(None)` 추가
- [ ] `schemas.LoginRequest.birth_date`를 필수(`str`)로 변경
- [ ] `routers/auth.py` 로그인에 6자리 숫자 형식 검증 추가
- [ ] `test_auth_bypass.py`를 401 기대로 뒤집기
- [ ] ✅ 검증: `{"name": "<SSO사용자>"}` 단독 요청 → 401
- [ ] ✅ 검증: `admin` / `000000` 로그인 → 200 유지
- [ ] ✅ 검증: `pytest` 전체 통과
- [ ] 📦 커밋: `fix: 생년월일 NULL 매칭을 통한 인증 우회 차단`

## Phase 2 — 배포 자격증명 분리 🔴

- [ ] `.env`에 `DEPLOY_HOST` / `DEPLOY_USER` / `DEPLOY_PASSWORD` 추가
- [ ] `deploy.py` — `.env` 직접 파싱 함수 작성 (의존성 추가 없이)
- [ ] `deploy.py` — 하드코딩된 `HOST` / `USERNAME` / `PASSWORD` 제거
- [ ] `deploy.py` — 값 누락 시 배포 시작 전 안내 메시지와 함께 종료
- [ ] ✅ 검증: `.env` 채운 상태로 `python deploy.py` 정상 완료
- [ ] ✅ 검증: `.env` 비운 상태로 실행 → 명확한 실패 메시지
- [ ] 📦 커밋: `refactor: 배포 스크립트 자격증명을 .env로 분리`
- [ ] ⚠️ **사용자 조치: 서버 계정 비밀번호 회전** (히스토리에 평문 잔존, 코드로 해결 불가)

## Phase 3 — SECRET_KEY 외부화 (무중단) 🟡

- [ ] `.env`에 `SECRET_KEY`(신규 랜덤 값) 추가
- [ ] `.env`에 `LEGACY_SECRET_KEY=bit_health_secret_key_2026` 추가
- [ ] `auth.py` — 발급은 항상 신규 키
- [ ] `auth.py` — 검증 시 신규 키 실패하면 레거시 키로 재시도, 둘 다 실패하면 401
- [ ] `auth.py` — 하드코딩 폴백 기본값 제거
- [ ] `docker-compose.yml` backend `environment`에 `SECRET_KEY`, `LEGACY_SECRET_KEY` 추가
- [ ] `deploy_docker_compose.yml`에 동일 적용
- [ ] `test_auth.py` — 레거시 키 서명 토큰 → 200
- [ ] `test_auth.py` — 신규 키 서명 토큰 → 200
- [ ] `test_auth.py` — 무관한 키 서명 토큰 → 401
- [ ] ✅ 검증: `pytest` 전체 통과
- [ ] ✅ 검증(배포 후): **기존 브라우저 세션이 로그아웃되지 않음**
- [ ] 📦 커밋: `fix: JWT 서명 키 외부화 및 무중단 전환용 레거시 키 검증 추가`
- [ ] 🗓 후속(2~4주 후 별도 커밋): 레거시 폴백 제거

## Phase 4 — 관리자 판정 하드코딩 제거 🟡

- [ ] 🔍 **선행 확인:** 운영 DB에서 관리자 계정의 `email`이 채워져 있는지 (`backend/check_users.py`)
- [ ] └ 비어 있으면 `ADMIN_EMAILS` 대신 `ADMIN_SUBS`(SSO sub 기준)로 전환
- [ ] `.env`에 `ADMIN_EMAILS` 추가
- [ ] `routers/auth.py:84` — 이름 하드코딩(`name == "이영배"`)을 환경변수 조회로 교체
- [ ] `routers/auth.py:97` — 기존 사용자 자동 승격 분기도 동일 기준으로 교체
- [ ] 승격만 하고 강등하지 않음(DB `role='admin'` 우선) 보장
- [ ] `docker-compose.yml` / `deploy_docker_compose.yml`에 `ADMIN_EMAILS` 추가
- [ ] `test_auth.py` — 목록에 있는 이메일 → `admin`
- [ ] `test_auth.py` — 동명이인(이름 같고 이메일 다름) → `user`
- [ ] `test_auth.py` — 기존 `role='admin'` 사용자는 유지
- [ ] ✅ 검증: 관리자 재로그인 후 `/admin` 접근 유지
- [ ] ✅ 검증: `/api/users/{id}/role` 수동 부여 경로 정상
- [ ] 📦 커밋: `fix: SSO 관리자 판정을 이름 하드코딩에서 환경변수 기반으로 변경`

## Phase 5 — 타임존 정합 🟡

- [ ] `models.py` — `User.created_at`의 `default=datetime.utcnow` → KST naive로 정정
- [ ] `models.py` — `AccessLog.check_in_time`의 기본값 동일 정정 (미발화 확인됨, 선언 정합용)
- [ ] `users.py:148-162` — tz-aware KST → naive `datetime.now()` 기준으로 변경
- [ ] `test_dashboard.py` — KST 월초 00:00 직후 경계 테스트
- [ ] `test_dashboard.py` — KST 월말 23:59 경계 테스트
- [ ] ❌ 백필하지 않음 (과거 행의 기준 판별 불가, 리스크 > 이득)
- [ ] ✅ 검증: `pytest` 전체 통과
- [ ] 📦 커밋: `fix: 타임존 기준을 KST naive로 통일`

## Phase 6 — 잔여 정리 🟢

- [ ] `main.py:37` 개발 중 메모 삭제
- [ ] `admin.py:3-4` 중복 import 정리
- [ ] `lib/api.ts:1` 폴백을 `http://localhost:8002`로 변경 (운영은 compose 주입으로 무영향)
- [ ] ❌ `golf.py:220` 미사용 패널티 주석은 그대로 둠 (의도적 비즈니스 결정)
- [ ] 📦 커밋: `chore: 개발 중 메모 및 중복 import 정리`
- [ ] 💬 보고만 (삭제는 승인 후): `lib/auth.ts:login()`, `/api/users/upload`, `/api/admin/dashboard/golf-reservations`, `/api/admin/golf/available-times`

## Phase 7 — 통합 검증 및 배포

- [ ] `cd backend && pytest` 전체 통과
- [ ] `docker compose up -d --build` 로컬 기동
- [ ] 수동: SSO 로그인 → 메인 대시보드 → 헬스 인원 표시
- [ ] 수동: `/access` 입실 → 퇴실
- [ ] 수동: `/golf` 예약 생성 → 선점 시나리오 → 취소
- [ ] 수동: `/admin` 통계 조회, 사용자 권한 변경
- [ ] `python deploy.py`
- [ ] 원격 스모크: `https://book.bit.kr` 로그인
- [ ] 원격 스모크: **기존 브라우저 세션 유지 확인** (Phase 3 핵심 검증)
- [ ] 원격 스모크: 예약 1건 생성, Slack 알림 수신
- [ ] `fetch_remote_logs.py`로 스케줄러 정상 동작 확인
- [ ] README 갱신 (환경변수 목록, 테스트 실행 방법)
