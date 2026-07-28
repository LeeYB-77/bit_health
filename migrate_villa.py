"""
마이그레이션: 비트별장(휴양소) 예약 기능
- villa_booking_rounds, villa_reservations 테이블 생성
- 청평별장/동비재 시설 시드 (정원 20명)
- villa_settings 기본 설정 시드 (7·8월 2박 제한)

테이블 자체는 배포 시 main.py의 Base.metadata.create_all()이 만들지만,
시드 데이터는 자동 생성되지 않으므로 이 스크립트가 필요하다.
멱등하게 작성되어 여러 번 실행해도 안전하다.
"""
import paramiko

# 접속 정보는 .env에서 읽는다. remote_config 참조
from remote_config import HOST, PORT, USERNAME, PASSWORD

SQL_COMMANDS = [
    # 1. 정규예약 회차 테이블
    """
    CREATE TABLE IF NOT EXISTS villa_booking_rounds (
        id SERIAL PRIMARY KEY,
        target_year INTEGER,
        target_month INTEGER,
        apply_start DATE,
        apply_end DATE,
        notify_date DATE,
        status VARCHAR DEFAULT 'open',
        reminder_sent BOOLEAN DEFAULT FALSE,
        notify_warning_sent BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP
    );
    """,
    # 이미 테이블이 있는 환경을 위한 보강 (멱등)
    "ALTER TABLE villa_booking_rounds ADD COLUMN IF NOT EXISTS reminder_sent BOOLEAN DEFAULT FALSE;",
    "ALTER TABLE villa_booking_rounds ADD COLUMN IF NOT EXISTS notify_warning_sent BOOLEAN DEFAULT FALSE;",
    "CREATE INDEX IF NOT EXISTS ix_villa_booking_rounds_target_year ON villa_booking_rounds (target_year);",
    "CREATE INDEX IF NOT EXISTS ix_villa_booking_rounds_target_month ON villa_booking_rounds (target_month);",

    # 2. 예약 신청 테이블
    """
    CREATE TABLE IF NOT EXISTS villa_reservations (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        facility_id INTEGER REFERENCES facilities(id),
        start_date DATE,
        end_date DATE,
        checkin_time VARCHAR,
        checkout_time VARCHAR,
        participant_count INTEGER DEFAULT 1,
        status VARCHAR DEFAULT 'applied',
        booking_type VARCHAR DEFAULT 'regular',
        round_id INTEGER REFERENCES villa_booking_rounds(id),
        created_at TIMESTAMP,
        confirmed_at TIMESTAMP,
        confirmed_by INTEGER REFERENCES users(id),
        notified_confirmed BOOLEAN DEFAULT FALSE,
        cancel_requested_at TIMESTAMP,
        cancel_reason TEXT,
        canceled_at TIMESTAMP,
        canceled_by INTEGER REFERENCES users(id),
        vehicle_count INTEGER,
        vehicle_numbers TEXT,
        adult_count INTEGER,
        child_count INTEGER,
        extra_info_updated_at TIMESTAMP,
        requested_checkin_time VARCHAR,
        requested_checkout_time VARCHAR,
        checkin_time_forced BOOLEAN DEFAULT FALSE,
        checkout_time_forced BOOLEAN DEFAULT FALSE
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_villa_reservations_start_date ON villa_reservations (start_date);",
    "CREATE INDEX IF NOT EXISTS ix_villa_reservations_end_date ON villa_reservations (end_date);",
    "CREATE INDEX IF NOT EXISTS ix_villa_reservations_status ON villa_reservations (status);",

    # 이미 테이블이 있는 환경을 위한 보강 (멱등) — 입퇴실 시간 정규화 기능
    "ALTER TABLE villa_reservations ADD COLUMN IF NOT EXISTS requested_checkin_time VARCHAR;",
    "ALTER TABLE villa_reservations ADD COLUMN IF NOT EXISTS requested_checkout_time VARCHAR;",
    "ALTER TABLE villa_reservations ADD COLUMN IF NOT EXISTS checkin_time_forced BOOLEAN DEFAULT FALSE;",
    "ALTER TABLE villa_reservations ADD COLUMN IF NOT EXISTS checkout_time_forced BOOLEAN DEFAULT FALSE;",
    # 기존 행은 강제 이력이 없던 시절의 데이터이므로 신청 시간을 그대로 '요청 시간'으로 채운다.
    "UPDATE villa_reservations SET requested_checkin_time = checkin_time WHERE requested_checkin_time IS NULL;",
    "UPDATE villa_reservations SET requested_checkout_time = checkout_time WHERE requested_checkout_time IS NULL;",

    # 3. 별장 시설 시드 (정원 20명)
    """
    INSERT INTO facilities (name, type, capacity)
    SELECT '청평별장', 'villa', 20
    WHERE NOT EXISTS (SELECT 1 FROM facilities WHERE name = '청평별장');
    """,
    """
    INSERT INTO facilities (name, type, capacity)
    SELECT '동비재', 'villa', 20
    WHERE NOT EXISTS (SELECT 1 FROM facilities WHERE name = '동비재');
    """,

    # 4. villa_settings 기본값 시드 (정규 입퇴실 시간: 입실 14:00 / 퇴실 12:00)
    """
    INSERT INTO system_settings (key, value)
    SELECT 'villa_settings', '{"peak_months": [7, 8], "peak_max_nights": 2, "default_max_nights": null, "default_checkin_time": "14:00", "default_checkout_time": "12:00", "villas": {}}'
    WHERE NOT EXISTS (SELECT 1 FROM system_settings WHERE key = 'villa_settings');
    """,
    # 이미 villa_settings가 있던 환경(예전 기본값 15:00/11:00)의 정규 시간을 정정한다.
    # jsonb_set으로 두 키만 바꿔 villas별 주소/안내문 등 다른 값은 보존한다.
    """
    UPDATE system_settings
    SET value = (
        jsonb_set(
            jsonb_set(value::jsonb, '{default_checkin_time}', '"14:00"'),
            '{default_checkout_time}', '"12:00"'
        )
    )::text
    WHERE key = 'villa_settings';
    """,
]

VERIFY_SQL = (
    "SELECT name, type, capacity FROM facilities WHERE type = 'villa' ORDER BY id;"
)


def run_migration():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[연결] {HOST}에 접속 중...")
    ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD)
    print("[연결] 성공\n")

    failed = 0
    for i, sql in enumerate(SQL_COMMANDS, start=1):
        # 개행을 공백으로 눌러 한 줄 명령으로 전달한다.
        flat = " ".join(sql.split())
        cmd = f"docker exec bit_health_db psql -U bit_health_user -d bit_health_db -c \"{flat}\""
        print(f"[{i}/{len(SQL_COMMANDS)}] {flat[:70]}...")

        stdin, stdout, stderr = ssh.exec_command(cmd)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()

        if out:
            print(f"    → {out}")
        if err:
            print(f"    [오류] {err}")
            failed += 1

    print("\n[확인] 생성된 별장 시설")
    cmd = f"docker exec bit_health_db psql -U bit_health_user -d bit_health_db -c \"{VERIFY_SQL}\""
    stdin, stdout, stderr = ssh.exec_command(cmd)
    stdout.channel.recv_exit_status()
    print(stdout.read().decode("utf-8", errors="replace").strip())

    ssh.close()

    if failed == 0:
        print("\n[완료] 마이그레이션이 성공적으로 완료되었습니다.")
    else:
        print(f"\n[실패] {failed}개 명령에서 오류가 발생했습니다.")


if __name__ == "__main__":
    run_migration()
