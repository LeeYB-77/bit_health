# SMTP 메일 발송 유틸. 설정은 SystemSetting의 smtp_settings에서 읽고 비밀번호는 암호화 저장한다.
import json
import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from . import crypto_utils, models

logger = logging.getLogger(__name__)

SETTING_KEY = "smtp_settings"

# 조회 응답에서 비밀번호 자리에 넣는 값. 저장 시 이 값이 오면 기존 비밀번호를 유지한다.
MASKED = "••••••"

DEFAULT_SMTP_SETTINGS = {
    "host": "",
    "port": 587,
    "use_tls": True,
    "username": "",
    "password_encrypted": "",
    "from_name": "BIT Wellness Center",
    "from_email": "",
}

SMTP_TIMEOUT_SECONDS = 10


def load_settings(db: Session) -> dict:
    row = db.query(models.SystemSetting).filter(
        models.SystemSetting.key == SETTING_KEY
    ).first()
    merged = dict(DEFAULT_SMTP_SETTINGS)
    if row:
        merged.update(json.loads(row.value))
    return merged


def save_settings(db: Session, settings: dict) -> None:
    row = db.query(models.SystemSetting).filter(
        models.SystemSetting.key == SETTING_KEY
    ).first()
    value = json.dumps(settings, ensure_ascii=False)
    if row:
        row.value = value
    else:
        db.add(models.SystemSetting(key=SETTING_KEY, value=value))
    db.commit()


def is_configured(settings: dict) -> bool:
    return bool(settings.get("host") and settings.get("from_email"))


def _deliver(settings: dict, to_email: str, subject: str, body: str) -> None:
    password = ""
    if settings.get("password_encrypted"):
        password = crypto_utils.decrypt(settings["password_encrypted"])

    message = EmailMessage()
    message["Subject"] = subject
    from_email = settings["from_email"]
    from_name = settings.get("from_name") or ""
    message["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    message["To"] = to_email
    message.set_content(body)

    host = settings["host"]
    port = int(settings.get("port") or 587)

    # 465는 접속 시점부터 SSL이고, 587 등은 평문으로 붙은 뒤 STARTTLS로 승격한다.
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT_SECONDS)
    else:
        server = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SECONDS)

    with server:
        if port != 465 and settings.get("use_tls"):
            server.starttls()
        if settings.get("username"):
            server.login(settings["username"], password)
        server.send_message(message)


def send_mail_or_raise(db: Session, to_email: str, subject: str, body: str) -> None:
    """실패 원인을 호출자에게 전달한다. 관리자 테스트 발송처럼 원인을 보여줘야 할 때 쓴다."""
    if not to_email:
        raise ValueError("받는 사람 주소가 없습니다.")

    settings = load_settings(db)
    if not is_configured(settings):
        raise RuntimeError("SMTP 설정이 완료되지 않았습니다. 서버 주소와 발신 주소를 먼저 입력하세요.")

    _deliver(settings, to_email, subject, body)


def send_mail(db: Session, to_email: str, subject: str, body: str) -> bool:
    """
    예약 확정 통보처럼 백그라운드에서 보내는 경로용.
    메일 발송 실패가 호출자의 트랜잭션을 깨뜨리면 안 되므로 예외를 삼키고 로그만 남긴다.
    slack_utils와 같은 방침이다.
    """
    try:
        send_mail_or_raise(db, to_email, subject, body)
        return True
    except Exception as e:
        logger.error(f"메일 발송 실패 ({to_email}): {e}")
        return False
