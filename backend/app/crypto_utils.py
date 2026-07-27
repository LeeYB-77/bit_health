# 설정값(SMTP 비밀번호 등)을 대칭키로 암복호화하는 유틸
import os

from cryptography.fernet import Fernet, InvalidToken

ENV_KEY = "SETTINGS_ENCRYPTION_KEY"


class EncryptionUnavailable(RuntimeError):
    """암호화 키가 없거나 잘못되어 암복호화를 할 수 없는 상태."""


def _get_fernet() -> Fernet:
    """
    SECRET_KEY와 달리 import 시점에 실패시키지 않는다.
    메일은 부가 기능이라 키가 없다고 앱 전체(헬스·골프·별장 예약)가 죽으면
    가용성 손해가 보안 이득보다 크다. 실제로 암복호화가 필요한 순간에만 실패한다.
    """
    key = os.getenv(ENV_KEY)
    if not key:
        raise EncryptionUnavailable(
            f"{ENV_KEY} 환경변수가 없어 메일 설정을 사용할 수 없습니다. "
            "Fernet.generate_key()로 생성한 값을 .env에 추가하세요."
        )
    try:
        return Fernet(key.encode())
    except Exception as e:
        raise EncryptionUnavailable(f"{ENV_KEY} 형식이 올바르지 않습니다: {e}")


def is_available() -> bool:
    """관리자 화면에서 메일 설정 가능 여부를 안내하는 용도."""
    try:
        _get_fernet()
        return True
    except EncryptionUnavailable:
        return False


def encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise EncryptionUnavailable(
            "저장된 값을 복호화할 수 없습니다. 암호화 키가 변경되었다면 "
            "메일 비밀번호를 다시 입력해야 합니다."
        )
