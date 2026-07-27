# 비트별장 예약 기능 체크리스트

상세 근거는 [villa-feature-plan.md](villa-feature-plan.md), 작업 중 판단은 [villa-context-notes.md](villa-context-notes.md) 참조.

**진행 상태: Phase 1~3 완료 및 커밋. 테스트 149개 통과, 실 PostgreSQL·브라우저 검증 완료. Phase 4(관리자 확정) 대기.**

---

## Phase 1 — 스키마 및 기반 ✅ 완료

- [x] `models.py` — `VillaReservation` 추가 (Date 타입, `created_at`은 KST naive)
- [x] `models.py` — `VillaReservation`에 취소 승인 컬럼 4개 (`cancel_requested_at`, `cancel_reason`, `canceled_at`, `canceled_by`)
- [x] `models.py` — `VillaBookingRound` 추가
- [x] `schemas.py` — 신청/조회/추가입력/취소요청 Pydantic 스키마
- [x] `initial_data.py` — 청평별장·동비재 `type='villa'`, **capacity 20** 시드 추가
- [x] `initial_data.py` — `villa_settings` 기본값 시드 (`peak_months: [7,8]`, `peak_max_nights: 2`)
- [x] `migrate_villa.py` — 운영 DB 마이그레이션 스크립트 (`remote_config` 사용)
- [x] `conftest.py` — `facilities` 픽스처에 villa 2개 추가
- [x] ✅ 검증: 기존 93개 테스트 여전히 통과 (회귀 없음)
- [x] 📦 커밋: `feat: 비트별장 예약 스키마 및 시드 추가`

## Phase 2 — 신청·조회 API ✅ 완료

- [x] `routers/villa.py` 신규 — 라우터 등록 (`main.py`)
- [x] 회차 산출 로직 — 대상월 2개월 전 1일~말일
- [x] 겹침 판정 헬퍼 — `a.start < b.end and a.end > b.start` (체크아웃 배타)
- [x] `GET /api/villa/facilities` — 별장 목록 + 설정
- [x] `GET /api/villa/current-round` — 현재 접수중 회차
- [x] `GET /api/villa/calendar` — 확정/신청중/내신청 구분 반환
- [x] `POST /api/villa/apply` — 중복 신청 허용, 접수 기간 검증
- [x] `GET /api/villa/my` — 내 신청 목록
- [x] `POST /api/villa/cancel/{id}` — `applied` 상태만 즉시 취소
- [x] `POST /api/villa/cancel-request/{id}` — `confirmed` 상태 취소 요청 + 관리자 Slack 알림
- [x] 인원 상한 검증 (`capacity` 20명)
- [x] 성수기 연박 제한 — **기간이 7·8월을 하루라도 포함하면 2박까지**
- [x] 월말 걸침 연박 — 체크인 날짜 기준으로 회차 판정
- [x] ✅ 테스트: 겹침 경계 (`8/1~8/3` vs `8/3~8/5` 비충돌)
- [x] ✅ 테스트: 같은 기간 중복 신청 허용
- [x] ✅ 테스트: 접수 기간 외 정규신청 거부
- [x] ✅ 테스트: 성수기 판정 — `7/10~7/12` 허용 / `7/10~7/13` 거부 / `6/30~7/3` 거부 / `6/25~6/28` 허용 / `9/1~9/8` 허용
- [x] ✅ 테스트: 인원 초과(21명) 거부, 과거 날짜 거부
- [x] ✅ 테스트: `confirmed` 예약에 즉시 취소 시도 거부 (요청 경로로만 가능)
- [x] 📦 커밋: `feat: 비트별장 신청/조회 API 추가`

## Phase 3 — 사용자 UI ✅ 완료

- [x] `lib/api.ts` — villa API 클라이언트 함수 + 타입
- [x] `app/villa/page.tsx` — 별장 토글, 회차 배너, 월 달력
- [x] 달력 컴포넌트 — 순수 `Date` 연산, 외부 라이브러리 없음
- [x] 연박 bar 렌더링, 확정/신청중/내신청 색 구분, 범례
- [x] 신청 모달 — 체크인·체크아웃, 예상 입퇴실 시간, 인원
- [x] "내 신청 현황" 섹션 — 상태 배지, 추가입력 필요 표시
- [x] `app/page.tsx` — 스크린골프 옆에 "비트별장" 카드 추가
- [x] `app/page.tsx` — 이번 달 헬스장 출석을 골프 아래로 이동
- [x] 상단 요약의 출석 수치는 **그대로 유지** (중복 표시 확정)
- [x] ✅ 검증: `npx tsc --noEmit` 통과
- [x] ✅ 검증: 로컬에서 달력·신청 플로우 화면 확인
- [x] 📦 커밋: `feat: 비트별장 예약 달력 UI 및 메뉴 배치`

## Phase 4 — 관리자 확정 및 취소 승인

- [ ] `GET /api/villa/admin/applications` — 겹치는 신청을 그룹으로 묶어 반환
- [ ] 과거 이용 이력 횟수 집계 (공정성 판단 근거)
- [ ] `POST /api/villa/admin/confirm/{id}` — 확정 + 나머지 자동 `rejected`
- [ ] `GET/POST /api/villa/admin/rounds` — 회차 조회·수동 생성
- [ ] `GET /api/villa/admin/cancel-requests` — 승인 대기 취소 요청 목록
- [ ] `POST /api/villa/admin/cancel-approve/{id}` — `canceled` 전환, 기간 재개방
- [ ] `POST /api/villa/admin/cancel-reject/{id}` — `confirmed` 복귀
- [ ] `app/admin/villa/page.tsx` — 경합 그룹 나란히 표시, 확정 버튼
- [ ] `app/admin/villa/page.tsx` — **상단에 취소 요청 섹션** (방치되면 기간이 묶이므로 먼저 노출)
- [ ] `app/admin/page.tsx` — 비트별장 관리 카드 추가
- [ ] ✅ 테스트: 확정 시 겹치는 나머지만 `rejected`, 무관한 건은 유지
- [ ] ✅ 테스트: 일반 사용자 접근 차단
- [ ] ✅ 테스트: 이미 확정된 기간에 재확정 시도 거부
- [ ] ✅ 테스트: 취소 승인 후 같은 기간 선착순 신청 가능
- [ ] ✅ 테스트: 취소 반려 시 `confirmed` 복귀, 기간 유지
- [ ] 📦 커밋: `feat: 비트별장 관리자 확정 및 취소 승인 기능`

## Phase 5 — SMTP 설정 (암호화)

- [ ] `.env` — `SETTINGS_ENCRYPTION_KEY` 추가 (`Fernet.generate_key()`)
- [ ] `crypto_utils.py` 신규 — Fernet 암복호화. **키 부재 시 호출 시점에만 실패**(앱 기동은 정상)
- [ ] `email_utils.py` 신규 — `smtplib` 기반, 발송 실패를 삼키고 로그만 남김
- [ ] `GET /api/admin/smtp` — 비밀번호 마스킹 반환
- [ ] `POST /api/admin/smtp` — 마스킹 값이면 기존 비밀번호 유지
- [ ] `POST /api/admin/smtp/test` — 테스트 메일 발송
- [ ] `app/admin/smtp/page.tsx` — 설정 폼 + 연결 테스트 버튼
- [ ] `docker-compose.yml` / `deploy_docker_compose.yml` — `SETTINGS_ENCRYPTION_KEY` 주입
- [ ] `app/admin/page.tsx` — 메일 설정 카드 추가
- [ ] ✅ 테스트: 암복호화 왕복
- [ ] ✅ 테스트: GET 응답에 평문 비밀번호가 없음
- [ ] ✅ 테스트: 마스킹 값 POST 시 기존 비밀번호 보존
- [ ] ✅ 테스트: 암호화 키 없어도 앱 기동 정상 (메일만 비활성)
- [ ] 📦 커밋: `feat: SMTP 설정 및 비밀번호 암호화 저장`

## Phase 6 — 확정 통보 + 추가입력

- [ ] `villa_utils.py` 또는 `slack_utils.py` 확장 — 확정/미선정/취소승인/취소반려 통보 문구
- [ ] Slack DM + 메일 동시 발송, 추가입력 링크 포함
- [ ] `POST /api/villa/admin/notify/{round_id}` — 일괄 통보, `notified_confirmed` 플래그로 중복 방지
- [ ] `GET/POST /api/villa/{id}/extra` — 본인만, `confirmed` 상태만
- [ ] `app/villa/extra/[id]/page.tsx` — 차량대수·차량번호(동적)·성인·아동
- [ ] 성인+아동 불일치 시 경고 표시 (저장은 허용)
- [ ] ✅ 테스트: 타인 예약 추가입력 접근 시 403
- [ ] ✅ 테스트: `applied` 상태 예약에 추가입력 거부
- [ ] ✅ 테스트: 통보 중복 발송 방지
- [ ] 📦 커밋: `feat: 비트별장 확정 통보 및 추가입력 페이지`

## Phase 7 — 선착순 + 스케줄러

- [ ] 선착순 신청 — `booking_type='open'`, 즉시 `confirmed` (열린 항목 3 확정 후)
- [ ] 확정 기간과 겹치면 거부
- [ ] 선착순 확정 시에도 통보 + 추가입력 링크 발송
- [ ] `main.py` `scheduled_jobs()` 확장 — 매월 1일 회차 자동 생성
- [ ] 접수 마감 3일 전 관리자 리마인더
- [ ] 마감일 경과 시 `status='closed'`
- [ ] 통보일 자동 통보, 미확정 경합 남으면 보류 + 관리자 경고
- [ ] ⚠️ 1분 주기 실행이므로 모든 작업에 중복 실행 방지 플래그 필수
- [ ] ✅ 테스트: 선착순 즉시 확정, 겹침 거부
- [ ] ✅ 테스트: 회차 중복 생성 방지
- [ ] ✅ 테스트: 통보 보류 조건
- [ ] 📦 커밋: `feat: 비트별장 선착순 예약 및 회차 자동화`

## Phase 8 — 통합 검증 및 배포

- [ ] `cd backend && pytest` 전체 통과
- [ ] `docker compose up -d --build` 실제 PostgreSQL로 기동
- [ ] `migrate_villa.py` 로컬 검증 후 원격 실행
- [ ] 수동: 정규예약 신청 → 중복 경합 → 관리자 확정 → 통보 → 추가입력 전체 플로우
- [ ] 수동: 확정 후 취소 요청 → 관리자 승인 → 기간 재개방 확인
- [ ] 수동: 선착순 신청 플로우
- [ ] 수동: 7·8월 3박 신청이 거부되는지 확인
- [ ] 수동: SMTP 테스트 메일 실제 수신 확인
- [ ] 수동: Slack DM 실제 수신 확인
- [ ] 수동: 달력에서 확정/신청중 구분이 직관적인지 확인
- [ ] 기존 기능 회귀 확인 — 헬스 입퇴실, 골프 예약, 관리자 통계
- [ ] `README.md` — 환경변수 표에 `SETTINGS_ENCRYPTION_KEY` 추가, 별장 기능 설명
- [ ] `python deploy.py` 원격 배포 (⛔ 사용자 승인 필요)
- [ ] 배포 후 원격 스모크

---

## 확정된 사양

- 정원: 청평별장 20명 / 동비재 20명
- 연박 상한: 7·8월 최대 2박3일, 그 외 달 제한 없음
- 성수기 판정: **이용 기간이 7·8월과 겹치면 성수기 규칙 적용** (`6/30~7/3` 3박은 거부)
- 확정 후 취소: 관리자 승인 필요 (`cancel_requested` → 승인/반려)

## 남은 열린 항목 (기본안 있음, 이견 없으면 진행)

[villa-feature-plan.md](villa-feature-plan.md) 13절 참조. Phase 3에는 영향이 없다. 아래 항목은 해당 Phase 착수 전까지 확인하면 된다.

1. [ ] 선착순 즉시 확정 (Phase 7) — 기본안은 즉시 확정
2. [ ] 성인+아동 합계 불일치 처리 (Phase 6) — 기본안은 경고만
3. [ ] 통보일 미확정 건 처리 (Phase 7) — 기본안은 통보 보류 + 관리자 경고
4. [x] 취소 사유 필수 입력 여부 — **선택 입력으로 구현** (Phase 2 완료)

**해결:** 이번 달 출석 중복 표시는 **그대로 유지**한다(사용자 확정). 상단 요약과 카드 양쪽에 둔다.
