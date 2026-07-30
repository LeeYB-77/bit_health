# BIT Health (사내 복지시설 예약 및 관리 시스템)

이 문서는 BIT Health 프로젝트의 개요와 구조를 설명하기 위해 작성된 프로젝트 명세서(README)입니다.
향후 개발 및 유지보수 시 본 문서를 참고하여 프로젝트 구조와 실행 방법을 빠르게 파악할 수 있습니다.

## 📌 1. 프로젝트 개요
BIT Health는 사내 임직원들의 복지를 위한 **헬스장·스크린 골프장·비트별장(휴양소) 예약/관리 시스템**입니다. 직원들은 본 시스템을 통해 실시간으로 체육관 인원을 확인하고, 스크린 골프장과 회사 휴양소를 예약하며, 관리처에서는 장비·예약·알림 발송 계정 등을 관리할 수 있습니다.

## 🏗 2. 기술 스택 (Tech Stack)
### 프론트엔드 (Frontend)
- **프레임워크**: Next.js (React 기반)
- **스타일링**: Tailwind CSS
- **배포 포트**: 80 (내부망 접속용 `http://59.10.164.2`)

### 백엔드 (Backend)
- **프레임워크**: FastAPI (Python 기반 비동기 웹 프레임워크)
- **ORM / DB**: SQLAlchemy / PostgreSQL 15 
- **주요 라이브러리**: APScheduler (주기적 작업), requests (Slack API 통신), cryptography (SMTP 비밀번호 등 설정값 암호화 저장)
- **배포 포트**: 8000 (컨테이너 내부) / 8002 (외부 노출 포트)
- **데이터베이스 포트**: 5434 (Host) / 5432 (Container)

## 🎯 3. 주요 기능 (Core Features)

### 가. SSO(Single Sign-On) 로그인 연동
- 사내 인트라넷 시스템의 SSO 로그인 API를 연동하여 별도 회원가입 없이 로그인 처리.
- 처음 로그인하는 사용자는 자동으로 DB에 저장되며 세션 토큰을 발급받습니다.

### 나. 헬스장 장비 관리 (Gym Management)
- **사용자**: 현재 헬스장 이용 인원 실시간 확인, 장비 현황 목록 조회
- **관리자**: 장비 추가, 고장(수리중) 상태 변경, 엑셀 일괄 업로드 및 다운로드

### 다. 스크린 골프 예약 (Screen Golf Reservation)
- **예약 우선순위 시스템**: 
  1. `최우선 (비트 직원)`: 타인에 의해 취소되지 않음
  2. `우선 (직원+고객)`: 양보 슬롯만 교체 가능
  3. `양보 (직원+가족)`: 누구나 교체 가능
- 다중 연속 슬롯(1~4시간) 및 동반자 입력 지원.
- 3시간 전 교체 불가 제한 로직 적용.

### 라. 비트별장(휴양소) 예약 (Villa Reservation)
청평별장·동비재(속초) 두 곳을 대상으로 한다. `backend/app/routers/villa.py`에 핵심 로직이 모여 있다.
- **정규예약**: 이용월 2개월 전 1일~말일에 신청을 받는다. 같은 기간에 여러 명이 신청할 수 있고(경합), 마감 후 관리자가 확정자를 선정한다.
- **선착순**: 정규예약 마감 후 남은 날짜는 선착순으로 열리지만, 즉시 확정되지 않고 정규예약과 동일하게 관리자 확정을 거친다(중복 신청 자체는 막는다). 회차 생성·마감·통보는 `villa_scheduler.py`가 매시간 자동 처리한다.
- **입퇴실 경계 시간 강제**: 같은 날 한쪽이 퇴실하고 다른 쪽이 입실하면, 정리 시간을 위해 양쪽 모두 정규 입퇴실 시간(기본 14시/12시)을 따르도록 자동 전환하고 당사자에게 알린다.
- **확정 후 추가 입력**: 차량 대수/번호, 이용 인원(성인/아동), 현장 연락처(필수)를 입력한다.
- **이용료 안내**: 확정 통보에 1박 5만원 + 추가 1박당 3만원 구조로 계산한 금액과 입금 계좌·기한(확정 후 3일 이내)을 함께 안내한다.
- **이용안내 · 퇴실 체크사항**: 체크인 전날 이용안내 페이지 링크를 메일+슬랙으로, 체크아웃 당일 오전 7시에 퇴실 체크사항 페이지 링크를 슬랙으로 자동 발송한다(`villa_scheduler.py`). 체크사항 페이지는 항목별 체크박스와 특이사항 입력란을 제출하면 결과가 슬랙으로 별장 관리 담당자에게 전달된다. 안내 문구·출입방법·체크리스트 내용은 `backend/app/villa_content.py`에 별장별로 정리돼 있다.
- **별장 위임 관리자**: 전체 관리자(`role=admin`)가 아니어도 `is_villa_admin` 플래그를 가진 사용자는 비트별장 관리 화면(신청 확정, 취소 승인, 회차 관리)만 접근할 수 있다. 위임 관리자가 한 명이라도 지정되면 별장 관련 알림은 전체 관리자 대신 위임 관리자에게만 간다.

### 마. 메일(SMTP) 발송 설정
- 관리자 페이지(`/admin/smtp`)에서 별장 확정/취소 알림을 보낼 SMTP 계정을 설정한다.
- 비밀번호는 `SETTINGS_ENCRYPTION_KEY`로 암호화해 `system_settings` 테이블에 저장하며, 화면에는 다시 표시되지 않는다.
- 저장된 설정으로 실제 테스트 메일을 발송해 볼 수 있다.

### 바. Slack DM 알림 연동
- 백엔드 스케줄러(`APScheduler`)가 백그라운드에서 주기적으로 동작한다.
- 골프 예약 1시간 전 **사전 알림 DM 발송**, 우선순위에 의해 예약을 빼앗겼을 경우 **취소 안내 DM 발송**.
- 비트별장 신청 접수·확정·취소요청·이용안내·퇴실체크 등도 같은 방식으로 Slack(+메일) 알림을 보낸다.

## 🚀 4. 배포 및 실행 안내 (Deployment)

본 프로젝트는 Docker Compose를 활용하여 컨테이너화되어 원격 서버(59.10.164.2)에 배포됩니다.

### 배포(Deploy) 방법
로컬 머신의 프로젝트 최상단 디렉토리에서 아래 배포 스크립트를 실행하면 전체 소스코드가 원격 서버로 전송되고 Docker 이미지가 재빌드되어 실행됩니다.

```bash
python deploy.py
```

- **로컬 테스트용 구성 파일**: `docker-compose.yml`
- **운영 서버용 구성 파일**: `deploy_docker_compose.yml`
  - 배포 스크립트는 이 파일을 타겟 서버의 `docker-compose.yml`로 덮어씌워 실행합니다.
- `deploy.py`는 `docker compose down` 없이 `up -d --build`만 실행합니다. 빌드가 실패해도 기존 컨테이너가 그대로 떠 있어 서비스가 끊기지 않도록 하기 위함입니다(과거 `down`을 먼저 실행하다가 빌드 실패 시 사이트 전체가 내려가는 사고가 있었습니다).

### DB 스키마를 바꾸는 배포는 순서를 반드시 지킬 것
`models.py`에 컬럼/테이블을 추가했다면, **코드를 배포하기 전에 먼저 마이그레이션을 실행**해야 합니다. `Base.metadata.create_all()`은 새 테이블은 만들어 주지만 이미 있는 테이블에 컬럼을 추가해 주지는 않아서, 새 컬럼을 참조하는 코드가 먼저 배포되면 그 테이블을 건드리는 모든 API가 500 에러를 내며 죽습니다.

```bash
python migrate_villa.py   # 스키마 변경분을 먼저 반영
python deploy.py          # 그다음 코드 배포
```

| 스크립트 | 대상 |
|---|---|
| `migrate_villa.py` | 비트별장(휴양소) 테이블·컬럼·시드 데이터 |
| `migrate_golf_priority.py` | 골프 예약 우선순위 관련 스키마 |
| `migrate_slack_notified.py` | Slack 알림 발송 여부 플래그 |
| `migrate_sso_db.py` | SSO 로그인 전환 관련 스키마 |
| `migrate_remote_db.py` | 범용 원격 DB 마이그레이션 |

모든 마이그레이션 스크립트는 `ALTER TABLE ... IF NOT EXISTS` / `INSERT ... WHERE NOT EXISTS` 패턴으로 작성되어 있어 여러 번 실행해도 안전합니다(멱등).

## 📂 5. 주요 폴더 및 파일 구조
```
BIT_health/
├── backend/                       # FastAPI 백엔드
│   ├── app/
│   │   ├── main.py                # 실행 엔트리포인트 및 스케줄러 등록
│   │   ├── models.py              # DB 테이블 스키마 정의
│   │   ├── auth.py                # 인증/권한 (get_current_active_admin, get_current_villa_manager 등)
│   │   ├── routers/                # API 엔드포인트 (golf.py, gym.py, villa.py, users.py, admin.py 등)
│   │   ├── villa_notify.py        # 비트별장 알림(Slack DM + 메일) 조립·발송
│   │   ├── villa_scheduler.py     # 비트별장 회차 전이·이용안내·퇴실체크 발송 스케줄러
│   │   ├── villa_content.py       # 별장별 이용안내·체크리스트 정적 콘텐츠
│   │   ├── email_utils.py         # SMTP 메일 발송
│   │   ├── crypto_utils.py        # SETTINGS_ENCRYPTION_KEY 기반 설정값 암호화
│   │   └── slack_utils.py         # Slack API 연동 유틸리티
│   ├── tests/                     # pytest (SQLite 인메모리)
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                      # Next.js 프론트엔드
│   ├── app/
│   │   ├── admin/                 # 관리자용 페이지 (golf, users, villa, smtp 등)
│   │   ├── golf/                  # 스크린 골프 예약 페이지
│   │   ├── villa/                 # 비트별장 예약 페이지
│   │   │   ├── page.tsx           # 예약 신청/취소, 달력, 안내 모달
│   │   │   ├── extra/[id]/        # 확정 후 추가입력(차량·인원·연락처)
│   │   │   ├── guide/[id]/        # 이용안내 (체크인 전날 링크)
│   │   │   └── checkout/[id]/     # 퇴실 체크사항 (체크아웃 당일 링크)
│   │   └── login/                 # SSO 로그인 관련 페이지
│   ├── public/villas/              # 별장 사진, 출입방법 아이콘
│   └── lib/api.ts                 # 백엔드 연동 API 클라이언트
├── migrate_villa.py                # 비트별장 스키마·시드 마이그레이션
├── migrate_*.py                    # 그 외 원격 DB 마이그레이션 스크립트
├── deploy.py                       # 원격 서버 자동 배포 스크립트
├── deploy_docker_compose.yml       # 원격 서버용 Docker 구성 사항 (토큰 등 환경 변수 존재)
└── docker-compose.yml              # 로컬 테스트용 Docker 구성 사항
```

## 🚨 6. 개발 및 운영 시 중요 인지사항 (Important Notes)

프로젝트 유지보수를 위해 반드시 숙지해야 하는 트러블슈팅 및 구조적 특징들입니다.

### 1) 보안 토큰 (Slack 등) 관리 및 Secret Scanning 방지
- GitHub의 보안 정책으로 인해 소스 코드 파일(예: `docker-compose.yml`) 내부에 명시적인 토큰(`xoxb-106089...` 등)이 적혀있을 경우 **Git Push가 아예 차단**됩니다.
- 토큰들은 반드시 `.env` 파일에 기록하여 이용하며, `.gitignore`를 통해 Git 추적에서 제외시켜야 합니다.
- 다행히 `deploy.py` 배포 스크립트는 `.env`를 포함하여 서버로 압축 전송하도록 설계되어 있으므로 서버 컨테이너에는 안전하게 주입됩니다.

### 2) Caddy를 통한 HTTPS 자동 적용 (Let's Encrypt)
- 프론트엔드와 백엔드는 `Caddy` 웹서버 컨테이너를 거쳐 외부로 서비스됩니다. 
- `Caddyfile` 설정에 의해 `book.bit.kr` 도메인의 SSL 인증서 발급과 갱신 프로세스가 모두 자동화되어 있어 서버 포트 80번과 443번을 Caddy에 단독으로 할당해 두어야 합니다.

### 3) 프론트엔드 API URL 고정 원칙 (혼합 콘텐츠 방지)
- 배포 컨테이너 내 Next.js 환경 변수(`NEXT_PUBLIC_API_URL`)는 반드시 `https://book.bit.kr` 로 세팅되어야 합니다(`HTTP` IP 주소 사용 금지).
- 특히 **빌드 타임(`args`)에도 해당 주소가 주입되도록** Docker Compose에 설정해 두어야 프론트엔드 정적 파일이 올바른 호출을 수행합니다.

### 4) 카카오톡 등 In-App 브라우저 로그인 세션 분리 현상
- 사용자가 체육관 앞에서 QR 코드를 스캔하여 `https://book.bit.kr/access` 로 접속할 때, 카메라 앱이 네이버나 카카오 웹뷰(In-App Browser)로 창을 열면 기존 사파리/크롬 브라우저와 별도의 로컬 저장소(`localStorage`)를 가지게 됩니다.
- 이 때문에 "이중 로그인을 요구한다"고 오인할 수 있으나, 정상적인 보안 분리 동작입니다. 사용자에게는 **"기본 브라우저(Safari/Chrome)로 전환해서 열기"** 기능을 안내하는 것이 올바른 대응입니다.

### 5) SSO 콜백 URL은 `https`로 일치시킬 것
- 외부 SSO 서버(drive.bit.kr)에서 인증을 마친 뒤 프론트엔드로 리턴하는 콜백 주소(`redirect_uri`)는 로직 내부 코딩 시 무조건 `https://book.bit.kr/login/callback` 을 명시적으로 사용해야 중간에 HTTP -> HTTPS 리다이렉트를 타면서 생기는 토큰 분실 위험을 차단할 수 있습니다.

### 6) 비트별장 스케줄러는 "다운타임 복구"를 스스로 처리한다
- `villa_scheduler.py`는 매시간 실행될 때마다 현재 대상월뿐 아니라 그 직전 달(선착순 오픈 대상) 회차까지 함께 보장해서 만든다.
- 서버가 한 달가량 멈췄다 복구되더라도, 회차가 아예 생성되지 못해 그 달이 영영 닫힌 채로 남는 일이 없도록 설계되어 있다. 새로 생성된 회차의 마감일이 이미 지난 값이면 같은 실행 안에서 바로 마감·통보까지 처리된다.

### 7) 필수 환경 변수 (`.env`)
- 백엔드는 다음 값이 없으면 기동 시 명확한 오류로 중단됩니다. 최초 배포 전 `.env`에 반드시 채워야 합니다.

| 변수 | 용도 |
|---|---|
| `SLACK_BOT_TOKEN` | Slack DM 알림 발송 |
| `SECRET_KEY` | JWT 서명 키. 미설정 시 백엔드가 `RuntimeError`로 기동 중단 |
| `LEGACY_SECRET_KEY` | 서명 키 교체 시 기존 발급 토큰(만료 1년)을 계속 수용하기 위한 전환기 전용 키. 구 토큰이 자연 교체된 뒤(대략 2~4주) 제거 |
| `ADMIN_EMAILS` | SSO 로그인 시 관리자 권한을 부여할 이메일 목록(콤마 구분, 대소문자 무시). 승격만 하고 강등하지 않으므로 DB에 이미 `role='admin'`인 계정은 이 목록에서 빠져도 유지됨 |
| `SETTINGS_ENCRYPTION_KEY` | SMTP 비밀번호 등 `system_settings`에 저장되는 민감 값 암호화(Fernet) 키. 미설정 시 SMTP 비밀번호 저장 기능만 비활성화되고 나머지 기능은 정상 동작 |
| `PUBLIC_BASE_URL` | 비트별장 알림(확정/이용안내/퇴실체크) 메시지에 들어가는 링크의 기준 주소. 미설정 시 기본값 `https://book.bit.kr` |
| `DEPLOY_HOST` / `DEPLOY_USER` / `DEPLOY_PASSWORD` / `DEPLOY_PORT` | `deploy.py` 등 로컬 배포·운영 스크립트가 SSH로 접속할 원격 서버 정보 |
| `REMOTE_DATABASE_URL` | 로컬에서 원격 PostgreSQL에 직접 접속하는 `migrate_*.py` 스크립트용 |

### 8) 백엔드 테스트 실행
```bash
cd backend
pip install -r requirements-dev.txt
pytest
```
- SQLite 인메모리 DB로 동작하며 실제 서버·DB에 영향을 주지 않습니다.
- `get_db`가 `database.py`와 `auth.py` 양쪽에 중복 정의되어 있어, 새 라우터를 추가할 때 어느 쪽을 참조하는지 확인하고 `tests/conftest.py`의 `dependency_overrides`에도 반영해야 합니다.
