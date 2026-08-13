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

    # 별장 위임 관리자 플래그 (role='admin'과 별개로 비트별장만 관리)
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_villa_admin BOOLEAN DEFAULT FALSE;",

    # 입실 전날 이용안내(메일+슬랙), 퇴실일 오전 퇴실체크 링크(슬랙) 발송 여부 및 제출 결과
    "ALTER TABLE villa_reservations ADD COLUMN IF NOT EXISTS checkin_guide_sent BOOLEAN DEFAULT FALSE;",
    "ALTER TABLE villa_reservations ADD COLUMN IF NOT EXISTS checkout_reminder_sent BOOLEAN DEFAULT FALSE;",
    "ALTER TABLE villa_reservations ADD COLUMN IF NOT EXISTS checkout_checklist_checked TEXT;",
    "ALTER TABLE villa_reservations ADD COLUMN IF NOT EXISTS checkout_checklist_notes TEXT;",
    "ALTER TABLE villa_reservations ADD COLUMN IF NOT EXISTS checkout_checklist_submitted_at TIMESTAMP;",

    # 확정 후 추가 입력사항에 현장 연락처 추가
    "ALTER TABLE villa_reservations ADD COLUMN IF NOT EXISTS contact_phone VARCHAR;",

    # 주차등록 요청 메일을 받을 관리실 주소의 초기값.
    # 이미 값이 있으면 건드리지 않는다 — 관리자가 화면에서 바꾼 주소를 되돌리면 안 된다.
    """
    UPDATE system_settings
    SET value = jsonb_set(value::jsonb, '{parking_office_email}', '"lyb77@bit.kr"')::text
    WHERE key = 'villa_settings'
      AND (value::jsonb -> 'parking_office_email') IS NULL;
    """,

    # 키 불출/회수 관리
    "ALTER TABLE villa_reservations ADD COLUMN IF NOT EXISTS key_number VARCHAR;",
    "ALTER TABLE villa_reservations ADD COLUMN IF NOT EXISTS key_issued_at TIMESTAMP;",
    "ALTER TABLE villa_reservations ADD COLUMN IF NOT EXISTS key_returned_at TIMESTAMP;",

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
    # 안내페이지용 별장 주소/평수 시드. jsonb_set의 create_missing(기본 true)이
    # villas 하위 키가 없어도 새로 만들어주므로 기존 notice 등 다른 값은 보존된다.
    """
    UPDATE system_settings
    SET value = (
        jsonb_set(
            jsonb_set(value::jsonb, '{villas,청평별장,address}', '"경기도 가평군 설악면 유명로 2304-34 르메이에르청평빌라 103동 402호(F층 시드니Ⅱ)"'),
            '{villas,청평별장,size}', '"56평"'
        )
    )::text
    WHERE key = 'villa_settings';
    """,
    """
    UPDATE system_settings
    SET value = (
        jsonb_set(
            jsonb_set(value::jsonb, '{villas,동비재,address}', '"강원도 속초시 금호동 630 생모리츠아파트 102동 1201호(속초 청초호 앞에 위치)"'),
            '{villas,동비재,size}', '"51평"'
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
        flat = " ".join(sql.split())
        print(f"[{i}/{len(SQL_COMMANDS)}] {flat[:70]}...")

        # SQL을 -c "..." 쉘 인자로 넘기면, SQL 안의 JSON 큰따옴표가 바깥 쉘의
        # 큰따옴표와 충돌해 명령이 깨진다(실제로 겪은 문제 — 조용히 성공한 것처럼
        # 보이지만 값이 깨져 들어간다). stdin으로 그대로 흘려보내면 쉘 인용 문제
        # 자체가 없다.
        stdin, stdout, stderr = ssh.exec_command(
            "docker exec -i bit_health_db psql -U bit_health_user -d bit_health_db -v ON_ERROR_STOP=1"
        )
        stdin.write(sql)
        stdin.channel.shutdown_write()
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()

        if out:
            print(f"    → {out}")
        if err:
            # ON_ERROR_STOP=1이라 NOTICE 등 정보성 메시지도 stderr로 오지만 exit_code는 0이다.
            # 실제 실패 여부는 exit_code로만 판단한다.
            print(f"    [{'오류' if exit_code != 0 else '알림'}] {err}")
        if exit_code != 0:
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
