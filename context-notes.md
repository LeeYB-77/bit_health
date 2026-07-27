# BIT Health 개선 작업 — 컨텍스트 노트

작업 중 내린 결정과 그 이유를 계속 append한다. 다음 세션이 판단을 재도출하지 않고 이어받기 위한 문서다.

---

## 2026-07-27 — 사전 조사

### 조사로 확인한 사실 (계획의 전제)

**1. 레거시 로그인은 UI에 존재하지 않는다.**
`frontend/app/login/page.tsx`에는 SSO 버튼만 있다. `frontend/lib/auth.ts:login()`은 정의만 있고 호출처가 없다(grep 확인). `/api/auth/login`의 실제 소비자는 `backend/test_login.py`와 `backend/debug_remote_access.py` 개발 스크립트뿐이다.
→ 인증 우회 수정의 사용자 영향이 0이므로 Phase 1을 최우선으로 올릴 수 있었다. 만약 UI에 폼이 살아 있었다면 SSO 미등록 사용자의 로그인 경로를 먼저 마련해야 했을 것이다.

**2. `AccessLog.check_in_time`의 `default=datetime.utcnow`는 발화하지 않는다.**
`gym.py:92`와 `golf.py:357` 모두 `check_in_time=datetime.now()`를 명시 전달한다. 컨테이너는 `TZ=Asia/Seoul`이므로 저장된 값은 KST naive로 이미 일관되다.
→ 타임존 문제의 실제 범위가 "선언과 실제의 불일치" + "대시보드의 aware/naive 혼용 비교" 두 가지로 좁혀졌다. 데이터 백필이 불필요하다는 판단의 근거다.

**3. `get_db`가 두 곳에 중복 정의되어 있다.**
`database.py:15`와 `auth.py:27`에 각각 있고, 라우터가 서로 다른 쪽을 import한다. `gym.py`/`golf.py`는 `..database.get_db`, `users.py`는 `auth.get_db`, `admin.py`는 `database.get_db`를 쓴다.
→ 테스트에서 `app.dependency_overrides`를 **양쪽 모두** 등록해야 한다. 한쪽만 등록하면 일부 라우터가 실제 PostgreSQL에 붙으려 해서 조용히 실패한다. Phase 0의 가장 흔한 함정.

**4. 모델에 PostgreSQL 전용 타입이 없다.**
JSONB/ARRAY 미사용. `SystemSetting.value`도 `Text`에 JSON 문자열을 담는 방식이다.
→ 테스트를 SQLite in-memory로 구성 가능. 단 최종 검증은 Phase 7에서 실제 PostgreSQL로 한다.

**5. 엑셀 업로드 UI가 없다.**
`/api/users/upload` 엔드포인트는 있으나 `frontend/app/admin/users/page.tsx`에 대응 UI가 없다(`birth_date`는 타입 정의에만 등장).
→ 이 계획에서 건드리지 않는다. 죽은 코드 목록에 보고만 한다.

### 결정과 이유

**결정 1. 회귀 테스트를 Phase 0으로 선행한다.**
"기존 작동에 문제 없도록"이라는 제약을 만족했다고 **증명할 수단**이 현재 없다. 테스트를 나중에 쓰면 이미 바뀐 동작을 고정하게 되어 의미가 없다. 특성화 테스트를 먼저 써서 현재 동작을 기준선으로 박는다.
→ `test_auth_bypass.py`는 예외적으로 **취약한 현재 동작을 200 기대로** 먼저 고정한다. Phase 1에서 401로 뒤집는 diff가 곧 수정의 증거가 된다.

**결정 2. `/api/auth/login`을 삭제하지 않고 가드를 추가한다.**
삭제가 더 깔끔하지만 `test_login.py`·`debug_remote_access.py`와 `admin/000000` 계정 접근이 끊긴다. `crud`에 `birth_date.isnot(None)` 한 줄 + 형식 검증으로 우회는 완전히 막히고 기존 경로는 보존된다. CLAUDE.md #3(surgical) 기준으로 가드가 맞다.
→ 향후 `/api/auth/login` 자체를 폐기하기로 결정한다면 dev 스크립트 2개를 함께 정리해야 한다.

**결정 3. SECRET_KEY는 이중 키로 무중단 전환한다.**
토큰 만료가 1년(`ACCESS_TOKEN_EXPIRE_MINUTES = 60*24*365`)이고 localStorage에 저장된다. 키를 그냥 교체하면 전 직원이 강제 로그아웃되어 제약을 위배한다. 검증 시 신규 키 → 실패하면 레거시 키 재시도 구조로 기존 토큰을 계속 수용한다.
→ 레거시 폴백은 **영구 유지하면 안 된다.** 하드코딩 키가 소스와 히스토리에 남아 있어 폴백이 살아 있는 동안은 그 키로 위조한 토큰도 통과한다. 2~4주 후 제거를 별도 커밋으로 잡아둔 이유다. 이 후속 작업을 잊으면 개선 효과가 절반이 된다.

**결정 4. 관리자 판정은 승격만 하고 강등하지 않는다.**
`ADMIN_EMAILS` 설정이 잘못되거나 SSO payload에 email이 없어도 DB의 `role='admin'`이 남아 있어 관리자 접근을 잃지 않는다. 권한 로직을 바꾸면서 스스로를 락아웃하는 것이 가장 흔한 사고다.
→ **미해결 불확실성:** 운영 DB에 관리자 계정의 `email`이 실제로 채워져 있는지 확인하지 못했다. `routers/auth.py:78`에서 SSO payload의 `email`을 받지만 payload에 없으면 NULL이다. Phase 4 착수 전 `backend/check_users.py`로 확인해야 하고, NULL이면 `ADMIN_SUBS`(SSO `sub` 기준)로 설계를 바꾼다.

**결정 5. 타임존 데이터를 백필하지 않는다.**
`User.created_at`의 과거 행은 UTC 기준이라 9시간 이르게 표시된다. 하지만 어느 행이 UTC이고 어느 행이 KST인지 판별할 근거가 없다(코드 변경 시점을 커밋 날짜로 추정할 수는 있으나 배포 시점과 다르다). 표시 전용 값에 판별 불가능한 일괄 보정을 넣으면 새 오류를 만든다. 리스크 > 이득.

**결정 6. git 히스토리를 재작성하지 않는다.**
`deploy.py`의 평문 비밀번호는 `.env`로 옮겨도 히스토리에 남는다. filter-branch/BFG는 원격 저장소와 다른 클론을 깨뜨리는데, 실질적 해결은 **비밀번호 회전**이다. 회전하면 히스토리의 값은 무효한 문자열이 된다.
→ 이건 코드로 못 하는 사용자 조치다. checklist에 ⚠️로 표시했다.

**결정 7. `.env` 파싱을 직접 구현한다(python-dotenv 미도입).**
`deploy.py`는 로컬 전용 스크립트이고, 필요한 건 `KEY=VALUE` 파싱 6줄이다. CLAUDE.md #2(최소 코드) 기준으로 의존성 추가는 과하다.

### 의도적으로 손대지 않는 것

- **`golf.py:220` 미사용 패널티 주석** — "사용자 요청"으로 중단된 비즈니스 결정. 재활성화는 정책 판단이다.
- **JWT 만료 1년 단축** — 축소하면 재로그인이 발생한다. 제약("기존 작동 무영향")과 충돌하므로 별건 판단 사항으로 분리했다.
- **Alembic 도입** — `create_all` + 수동 `migrate_*.py`로 운영 중. 개선 가치는 있지만 요청 범위를 넘는 구조 변경이다.
- **죽은 코드 삭제** — `lib/auth.ts:login()`, `/api/users/upload`, `/api/admin/dashboard/golf-reservations`, `/api/admin/golf/available-times`. CLAUDE.md #3에 따라 보고만 하고 승인 후 처리한다.

### 다음 세션이 알아야 할 것

1. Phase 0의 `conftest.py`에서 `get_db` **양쪽 오버라이드**를 잊지 말 것 (위 사실 3).
2. Phase 4 착수 전 관리자 계정의 `email` NULL 여부를 반드시 확인할 것 (결정 4의 미해결 불확실성).
3. Phase 3의 레거시 키 폴백 제거는 **별도 후속 작업**이며, 잊으면 개선이 미완성이다.
4. Phase 7의 원격 스모크에서 "기존 브라우저 세션 유지"가 Phase 3 설계의 유일한 실증 검증이다. 새 시크릿 창으로 테스트하면 의미가 없다.

---

## 2026-07-27 — 실행 결과 (Phase 0~7)

전 단계를 `improve/security-and-timezone` 브랜치에서 순서대로 실행, 각 Phase 1커밋으로 마무리했다. 원격 배포(`python deploy.py`)는 실행하지 않았다 — SSH로 운영 서버를 재기동하는 외향적 행동이라 사용자 확인 없이 진행하지 않았다.

### 계획과 실제가 갈린 지점

**Phase 2가 계획보다 훨씬 커졌다.** 사전 조사 때는 `deploy.py`만 봤는데, 실제로 grep해보니 동일한 SSH 비밀번호(`bitcom1983!`)가 `check_remote_status.py`, `cleanup_remote_db.py`, `debug_remote.py`, `fetch_remote_logs.py`, `init_remote_db.py`, `migrate_golf_priority.py`, `migrate_slack_notified.py` 등 7개 파일에 더 하드코딩되어 있었다. `deploy.py` 하나만 고쳤다면 노출이 그대로 남는 상황이었다. `remote_config.py`라는 공용 모듈을 만들어 8개 파일 전부가 참조하도록 했다. `migrate_remote_db.py`/`migrate_sso_db.py`는 SSH가 아니라 DB 접속 문자열을 직접 하드코딩하고 있어 `REMOTE_DATABASE_URL`이라는 별도 키로 분리했다.

**Phase 4 선행 확인에서 예상보다 심각한 사실을 발견했다.** 운영 DB를 읽기 전용으로 직접 조회한 결과:
- 전체 45명 중 **43명이 `birth_date` NULL** (SSO 사용자 전원)
- 관리자 4명 중 2명은 레거시(id=2 이영배, id=3 조현정, birth_date 있음), 2명은 SSO(id=144 lyb77@bit.kr, id=147 hjcho@bit.kr)
- **동명이인이 실제로 2건 존재**(이영배, 조현정 각각 레거시+SSO 계정)

즉 Phase 1이 막은 것과 Phase 4가 막은 것 둘 다 "이론적 취약점"이 아니라 "운영 데이터에 이미 그 조건이 존재하는 상태"였다. 특히 Phase 1 수정 전에는 `{"name":"이영배"}` 한 줄로 id=144 관리자 계정에 로그인이 가능했다 — 이름은 동료에게 공개된 정보라 진입장벽이 사실상 없었다.

이 조회로 `ADMIN_EMAILS` 설계가 그대로 유효함을 확인했다(`ADMIN_SUBS` 대안 불필요, SSO 사용자 전원 email 보유).

### Phase 7 로컬 통합 검증에서 실제로 확인한 것

Docker Desktop이 최초 꺼져 있어 기동 후 `docker compose up -d --build`로 실제 PostgreSQL 15 컨테이너를 띄우고 API를 직접 호출했다. SQLite 유닛테스트로는 드러나지 않는 것들을 이 단계에서 확인했다.

- **Phase 5의 핵심 리스크였던 tz-aware/naive 비교 버그가 실제로 고쳐졌는지**: 오늘 헬스 입실 → `/api/users/me/dashboard`가 `monthly_count: 1` 반환, 오늘 골프 예약 → `has_today_reservation: true` 반환. 둘 다 정상. `User.created_at`도 KST 벽시계 시각(13:51)과 일치해 표시됐다.
- **Phase 3의 무중단 전환**: 레거시 키(`bit_health_secret_key_2026`)로 서명한 토큰이 여전히 `/api/users/me`에서 200을 받았고, 무관한 키로 서명한 토큰은 401로 거부됐다. 설계대로 동작.
- **컨테이너 환경변수 주입**: `SECRET_KEY`, `LEGACY_SECRET_KEY`, `ADMIN_EMAILS`, `SLACK_BOT_TOKEN` 전부 `docker exec printenv`로 확인.
- 사소한 이슈: backend 컨테이너가 db보다 먼저 접속을 시도해 첫 기동에서 크래시했다. `restart: always`가 있지만 uvicorn `--reload` 프로세스 특성상 자동 복구가 즉시 안 일어나 `docker compose restart backend`를 한 번 수동 실행해야 했다. 운영 배포 시 동일 증상이 나올 수 있으니 참고.

**실행하지 않고 남긴 것**: 실제 SSO 로그인 플로우(drive.bit.kr 실서버 필요, 로컬 재현 불가)와 `python deploy.py` 원격 배포. 둘 다 사용자 확인이 필요한 지점이라 checklist.md의 "남은 것" 섹션에 명시했다.
