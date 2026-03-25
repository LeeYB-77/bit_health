"""
마이그레이션: 예약 1시간 전 Slack 알림 기능
- reservations 테이블에 notified_slack 컬럼 추가 (기본값 FALSE)
"""
import paramiko

HOST = '59.10.164.2'
PORT = 22
USERNAME = 'bitcom'
PASSWORD = 'bitcom1983!'

SQL_COMMANDS = [
    "ALTER TABLE reservations ADD COLUMN IF NOT EXISTS notified_slack BOOLEAN DEFAULT FALSE;"
]

def run_migration():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[연결] {HOST}에 접속 중...")
    ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD)
    print("[연결] 성공")

    # 단일 exec_command로 실행하여 KeyboardInterrupt 이슈 방지
    sql = "ALTER TABLE reservations ADD COLUMN IF NOT EXISTS notified_slack BOOLEAN DEFAULT FALSE;"
    cmd = f"docker exec bit_health_db psql -U bit_health_user -d bit_health_db -c \"{sql}\""
    print(f"[실행] {cmd}")
    
    stdin, stdout, stderr = ssh.exec_command(cmd)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    
    if out:
        print(f"  → {out}")
    if err:
        print(f"  [오류] {err}")
    
    print(f"  종료 코드: {exit_code}")
    ssh.close()
    
    if exit_code == 0:
        print("\n[완료] 마이그레이션이 성공적으로 완료되었습니다.")
    else:
        print("\n[실패] 마이그레이션 중 오류가 발생했습니다.")

if __name__ == "__main__":
    run_migration()
