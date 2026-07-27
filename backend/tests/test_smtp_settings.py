# SMTP 설정 저장·조회와 비밀번호 암호화 동작을 고정하는 테스트
import json

import pytest

from app import crypto_utils, email_utils, models

VALID_PAYLOAD = {
    "host": "smtp.bit.kr",
    "port": 587,
    "use_tls": True,
    "username": "noreply@bit.kr",
    "password": "super-secret-1234",
    "from_name": "BIT Wellness Center",
    "from_email": "noreply@bit.kr",
}


def _stored(db):
    row = db.query(models.SystemSetting).filter(
        models.SystemSetting.key == email_utils.SETTING_KEY
    ).first()
    return json.loads(row.value) if row else None


# --- 암복호화 ---

def test_암복호화_왕복():
    token = crypto_utils.encrypt("super-secret-1234")
    assert token != "super-secret-1234"
    assert crypto_utils.decrypt(token) == "super-secret-1234"


def test_같은_평문도_매번_다른_암호문(monkeypatch):
    """Fernet은 타임스탬프와 IV를 포함하므로 암호문이 매번 달라진다."""
    assert crypto_utils.encrypt("same") != crypto_utils.encrypt("same")


def test_키가_없으면_호출_시점에만_실패(monkeypatch):
    """
    SECRET_KEY와 달리 import 시점에 죽지 않는다.
    메일은 부가 기능이라 키가 없어도 앱 전체는 살아 있어야 한다.
    """
    monkeypatch.delenv(crypto_utils.ENV_KEY, raising=False)
    assert crypto_utils.is_available() is False
    with pytest.raises(crypto_utils.EncryptionUnavailable):
        crypto_utils.encrypt("x")


def test_잘못된_형식의_키는_명확히_실패(monkeypatch):
    monkeypatch.setenv(crypto_utils.ENV_KEY, "not-a-valid-fernet-key")
    assert crypto_utils.is_available() is False
    with pytest.raises(crypto_utils.EncryptionUnavailable):
        crypto_utils.encrypt("x")


def test_다른_키로_만든_암호문은_복호화_실패(monkeypatch):
    from cryptography.fernet import Fernet
    other = Fernet.generate_key().decode()
    monkeypatch.setenv(crypto_utils.ENV_KEY, other)
    token = crypto_utils.encrypt("secret")

    monkeypatch.setenv(crypto_utils.ENV_KEY, "BFrPS8DP_HexSFzWnhcDk-evhABp1Yp963uKIeXcpYA=")
    with pytest.raises(crypto_utils.EncryptionUnavailable):
        crypto_utils.decrypt(token)


def test_암호화_키_없어도_앱은_정상_동작(client, facilities, make_user, auth_headers, monkeypatch):
    """메일만 비활성되고 헬스·별장 등 다른 기능은 그대로 동작해야 한다."""
    monkeypatch.delenv(crypto_utils.ENV_KEY, raising=False)

    assert client.get("/api/gym/status", headers=auth_headers(make_user())).status_code == 200
    assert client.get("/api/villa/facilities", headers=auth_headers(make_user())).status_code == 200

    body = client.get("/api/admin/smtp", headers=auth_headers(make_user(role="admin"))).json()
    assert body["encryption_available"] is False


# --- 설정 조회 ---

def test_초기_설정은_비어있음(client, make_user, auth_headers):
    body = client.get("/api/admin/smtp", headers=auth_headers(make_user(role="admin"))).json()
    assert body["host"] == ""
    assert body["password"] == ""
    assert body["password_set"] is False
    assert body["configured"] is False
    assert body["encryption_available"] is True


def test_설정은_관리자_전용(client, make_user, auth_headers):
    user = auth_headers(make_user())
    assert client.get("/api/admin/smtp", headers=user).status_code == 403
    assert client.post("/api/admin/smtp", headers=user, json=VALID_PAYLOAD).status_code == 403
    assert client.post("/api/admin/smtp/test", headers=user, json={"to_email": "a@bit.kr"}).status_code == 403


# --- 저장 ---

def test_비밀번호는_암호화되어_저장된다(client, db, make_user, auth_headers):
    res = client.post("/api/admin/smtp", headers=auth_headers(make_user(role="admin")), json=VALID_PAYLOAD)
    assert res.status_code == 200

    saved = _stored(db)
    assert saved["host"] == "smtp.bit.kr"
    # 평문이 DB에 남으면 안 된다
    assert "super-secret-1234" not in json.dumps(saved)
    assert saved["password_encrypted"]
    assert crypto_utils.decrypt(saved["password_encrypted"]) == "super-secret-1234"
    # 평문 키 자체가 없어야 한다
    assert "password" not in saved


def test_조회_응답에_평문도_암호문도_없다(client, db, make_user, auth_headers):
    headers = auth_headers(make_user(role="admin"))
    client.post("/api/admin/smtp", headers=headers, json=VALID_PAYLOAD)

    res = client.get("/api/admin/smtp", headers=headers)
    raw = res.text
    body = res.json()

    assert "super-secret-1234" not in raw
    assert _stored(db)["password_encrypted"] not in raw
    assert body["password"] == email_utils.MASKED
    assert body["password_set"] is True
    assert body["configured"] is True


def test_마스킹_값으로_저장하면_기존_비밀번호_유지(client, db, make_user, auth_headers):
    headers = auth_headers(make_user(role="admin"))
    client.post("/api/admin/smtp", headers=headers, json=VALID_PAYLOAD)
    before = _stored(db)["password_encrypted"]

    # 화면에서 비밀번호를 건드리지 않고 다른 항목만 바꿔 저장하는 상황
    payload = {**VALID_PAYLOAD, "password": email_utils.MASKED, "host": "smtp2.bit.kr"}
    client.post("/api/admin/smtp", headers=headers, json=payload)

    after = _stored(db)
    assert after["host"] == "smtp2.bit.kr"
    assert after["password_encrypted"] == before
    assert crypto_utils.decrypt(after["password_encrypted"]) == "super-secret-1234"


def test_password_생략해도_기존_비밀번호_유지(client, db, make_user, auth_headers):
    headers = auth_headers(make_user(role="admin"))
    client.post("/api/admin/smtp", headers=headers, json=VALID_PAYLOAD)
    before = _stored(db)["password_encrypted"]

    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "password"}
    client.post("/api/admin/smtp", headers=headers, json=payload)

    assert _stored(db)["password_encrypted"] == before


def test_빈_문자열로_저장하면_비밀번호_제거(client, db, make_user, auth_headers):
    headers = auth_headers(make_user(role="admin"))
    client.post("/api/admin/smtp", headers=headers, json=VALID_PAYLOAD)

    client.post("/api/admin/smtp", headers=headers, json={**VALID_PAYLOAD, "password": ""})

    assert _stored(db)["password_encrypted"] == ""
    body = client.get("/api/admin/smtp", headers=headers).json()
    assert body["password_set"] is False


def test_비밀번호_변경(client, db, make_user, auth_headers):
    headers = auth_headers(make_user(role="admin"))
    client.post("/api/admin/smtp", headers=headers, json=VALID_PAYLOAD)
    client.post("/api/admin/smtp", headers=headers, json={**VALID_PAYLOAD, "password": "new-password"})

    assert crypto_utils.decrypt(_stored(db)["password_encrypted"]) == "new-password"


def test_암호화_키_없이_비밀번호_저장하면_400(client, make_user, auth_headers, monkeypatch):
    monkeypatch.delenv(crypto_utils.ENV_KEY, raising=False)
    res = client.post("/api/admin/smtp", headers=auth_headers(make_user(role="admin")), json=VALID_PAYLOAD)
    assert res.status_code == 400
    assert "SETTINGS_ENCRYPTION_KEY" in res.json()["detail"]


def test_필수값_누락은_422(client, make_user, auth_headers):
    headers = auth_headers(make_user(role="admin"))
    assert client.post("/api/admin/smtp", headers=headers, json={"host": "smtp.bit.kr"}).status_code == 422


# --- 발송 ---

def test_설정_없으면_발송_실패(client, db, make_user, auth_headers):
    res = client.post(
        "/api/admin/smtp/test",
        headers=auth_headers(make_user(role="admin")),
        json={"to_email": "a@bit.kr"},
    )
    assert res.status_code == 400
    assert "SMTP 설정" in res.json()["detail"]


def test_테스트_발송_성공(client, db, make_user, auth_headers, monkeypatch):
    headers = auth_headers(make_user(role="admin"))
    client.post("/api/admin/smtp", headers=headers, json=VALID_PAYLOAD)

    sent = {}

    def fake_deliver(settings, to_email, subject, body):
        sent.update(settings=settings, to=to_email, subject=subject, body=body)

    monkeypatch.setattr(email_utils, "_deliver", fake_deliver)

    res = client.post("/api/admin/smtp/test", headers=headers, json={"to_email": "target@bit.kr"})
    assert res.status_code == 200
    assert sent["to"] == "target@bit.kr"
    assert "테스트" in sent["subject"]
    assert sent["settings"]["host"] == "smtp.bit.kr"


def test_발송_실패_원인이_전달된다(client, db, make_user, auth_headers, monkeypatch):
    headers = auth_headers(make_user(role="admin"))
    client.post("/api/admin/smtp", headers=headers, json=VALID_PAYLOAD)

    def boom(*a, **kw):
        raise OSError("Connection refused")

    monkeypatch.setattr(email_utils, "_deliver", boom)

    res = client.post("/api/admin/smtp/test", headers=headers, json={"to_email": "a@bit.kr"})
    assert res.status_code == 400
    assert "Connection refused" in res.json()["detail"]


def test_백그라운드_발송은_예외를_삼킨다(db, monkeypatch):
    """예약 확정 통보가 메일 실패로 롤백되면 안 된다. slack_utils와 같은 방침."""
    email_utils.save_settings(db, {
        **email_utils.DEFAULT_SMTP_SETTINGS,
        "host": "smtp.bit.kr",
        "from_email": "noreply@bit.kr",
    })

    def boom(*a, **kw):
        raise OSError("Connection refused")

    monkeypatch.setattr(email_utils, "_deliver", boom)
    assert email_utils.send_mail(db, "a@bit.kr", "제목", "본문") is False


def test_백그라운드_발송_성공은_True(db, monkeypatch):
    email_utils.save_settings(db, {
        **email_utils.DEFAULT_SMTP_SETTINGS,
        "host": "smtp.bit.kr",
        "from_email": "noreply@bit.kr",
    })
    monkeypatch.setattr(email_utils, "_deliver", lambda *a, **kw: None)
    assert email_utils.send_mail(db, "a@bit.kr", "제목", "본문") is True


def test_받는사람_없으면_발송_안_함(db):
    assert email_utils.send_mail(db, "", "제목", "본문") is False


def test_발신자_표기(db, monkeypatch):
    """From 헤더가 '이름 <주소>' 형태로 조립되는지 확인한다."""
    captured = {}

    class FakeServer:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): captured["tls"] = True
        def login(self, u, p): captured["login"] = (u, p)
        def send_message(self, msg): captured["msg"] = msg

    monkeypatch.setattr(email_utils.smtplib, "SMTP", lambda *a, **kw: FakeServer())

    settings = {
        **email_utils.DEFAULT_SMTP_SETTINGS,
        "host": "smtp.bit.kr",
        "port": 587,
        "use_tls": True,
        "username": "noreply@bit.kr",
        "password_encrypted": crypto_utils.encrypt("pw"),
        "from_name": "BIT Wellness Center",
        "from_email": "noreply@bit.kr",
    }
    email_utils._deliver(settings, "target@bit.kr", "제목", "본문")

    assert captured["msg"]["From"] == "BIT Wellness Center <noreply@bit.kr>"
    assert captured["msg"]["To"] == "target@bit.kr"
    assert captured["tls"] is True
    # 복호화된 평문이 로그인에 쓰인다
    assert captured["login"] == ("noreply@bit.kr", "pw")


def test_465포트는_SSL로_접속(db, monkeypatch):
    used = {}

    class FakeServer:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): used["starttls"] = True
        def login(self, u, p): pass
        def send_message(self, msg): pass

    monkeypatch.setattr(email_utils.smtplib, "SMTP_SSL", lambda *a, **kw: (used.setdefault("ssl", True), FakeServer())[1])
    monkeypatch.setattr(email_utils.smtplib, "SMTP", lambda *a, **kw: (used.setdefault("plain", True), FakeServer())[1])

    settings = {
        **email_utils.DEFAULT_SMTP_SETTINGS,
        "host": "smtp.bit.kr", "port": 465, "use_tls": True,
        "from_email": "noreply@bit.kr", "username": "",
    }
    email_utils._deliver(settings, "target@bit.kr", "제목", "본문")

    assert used.get("ssl") is True
    assert "plain" not in used
    # SSL 접속에서는 STARTTLS를 다시 걸지 않는다
    assert "starttls" not in used
