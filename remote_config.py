# 원격 서버 접속 정보를 .env에서 읽어 로컬 운영 스크립트에 제공하는 공용 모듈
import os
import sys

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

_REQUIRED_KEYS = ("DEPLOY_HOST", "DEPLOY_USER", "DEPLOY_PASSWORD")


def _load_env(path):
    """의존성을 늘리지 않기 위해 KEY=VALUE 형식만 직접 파싱한다."""
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


_env = _load_env(_ENV_PATH)


def _get(key):
    # 셸 환경변수가 .env보다 우선한다.
    return os.getenv(key) or _env.get(key)


_missing = [key for key in _REQUIRED_KEYS if not _get(key)]
if _missing:
    sys.exit(
        "[설정 누락] 원격 접속 정보가 없어 실행을 중단합니다.\n"
        f"누락된 항목: {', '.join(_missing)}\n\n"
        "프로젝트 최상단 .env 파일에 아래 항목을 채워주세요.\n"
        "  DEPLOY_HOST=<서버 IP>\n"
        "  DEPLOY_USER=<계정>\n"
        "  DEPLOY_PASSWORD=<비밀번호>\n"
        "  DEPLOY_PORT=22            # 생략 가능\n"
        "  REMOTE_DATABASE_URL=...   # DB 직결 스크립트에서만 필요\n"
    )

HOST = _get("DEPLOY_HOST")
USERNAME = _get("DEPLOY_USER")
PASSWORD = _get("DEPLOY_PASSWORD")
PORT = int(_get("DEPLOY_PORT") or 22)


def require_database_url():
    """DB에 직접 접속하는 스크립트에서만 호출한다."""
    url = _get("REMOTE_DATABASE_URL")
    if not url:
        sys.exit(
            "[설정 누락] REMOTE_DATABASE_URL이 없어 실행을 중단합니다.\n"
            "프로젝트 최상단 .env에 아래 형식으로 추가해주세요.\n"
            "  REMOTE_DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<db>\n"
        )
    return url
