# BIT Health (사내 체육시설 예약 및 관리 시스템)

이 문서는 BIT Health 프로젝트의 개요와 구조를 설명하기 위해 작성된 프로젝트 명세서(README)입니다.
향후 개발 및 유지보수 시 본 문서를 참고하여 프로젝트 구조와 실행 방법을 빠르게 파악할 수 있습니다.

## 📌 1. 프로젝트 개요
BIT Health는 사내 임직원들의 복지를 위한 **헬스장 및 스크린 골프장 예약/관리 시스템**입니다. 직원들은 본 시스템을 통해 실시간으로 체육관 인원을 확인하고, 스크린 골프장을 예약하며, 관리처에서는 장비의 상태를 관리할 수 있습니다.

## 🏗 2. 기술 스택 (Tech Stack)
### 프론트엔드 (Frontend)
- **프레임워크**: Next.js (React 기반)
- **스타일링**: Tailwind CSS
- **배포 포트**: 80 (내부망 접속용 `http://59.10.164.2`)

### 백엔드 (Backend)
- **프레임워크**: FastAPI (Python 기반 비동기 웹 프레임워크)
- **ORM / DB**: SQLAlchemy / PostgreSQL 15 
- **주요 라이브러리**: APScheduler (주기적 작업), requests (Slack API 통신)
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

### 라. Slack DM 알림 연동
- 백엔드 스케줄러(`APScheduler`)가 백그라운드에서 주기적으로 도킹됨.
- 예약 1시간 전 **사전 알림 DM 발송**
- 우선순위에 의해 예약을 빼앗겼을 경우 **취소 안내 DM 발송**

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

## 📂 5. 주요 폴더 및 파일 구조
```
BIT_health/
├── backend/                  # FastAPI 백엔드
│   ├── app/
│   │   ├── main.py           # 실행 엔트리포인트 및 스케줄러
│   │   ├── models.py         # DB 테이블 스키마 정의
│   │   ├── routers/          # API 엔드포인트 (golf.py, gym.py 등)
│   │   └── slack_utils.py    # Slack API 연동 유틸리티
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                 # Next.js 프론트엔드
│   ├── app/
│   │   ├── admin/            # 관리자용 페이지
│   │   ├── golf/             # 스크린 골프 예약 페이지
│   │   └── login/            # SSO 로그인 관련 페이지
│   └── lib/api.ts            # 백엔드 연동 Axios API 클라이언트
├── deploy.py                 # 원격 서버 자동 배포 스크립트
├── deploy_docker_compose.yml # 원격 서버용 Docker 구성 사항 (토큰 등 환경 변수 존재)
└── docker-compose.yml        # 로컬 테스트용 Docker 구성 사항
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
