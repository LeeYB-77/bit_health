import paramiko
import sys

HOST = '59.10.164.2'
PORT = 22
USERNAME = 'bitcom'
PASSWORD = 'bitcom1983!'

sql_commands = """
DELETE FROM access_logs WHERE user_id NOT IN (SELECT MIN(id) FROM users WHERE name IN ('이영배', '조현정') GROUP BY name);
DELETE FROM reservations WHERE user_id NOT IN (SELECT MIN(id) FROM users WHERE name IN ('이영배', '조현정') GROUP BY name);
DELETE FROM users WHERE id NOT IN (SELECT MIN(id) FROM users WHERE name IN ('이영배', '조현정') GROUP BY name);
"""

command = f'docker exec bit_health_db psql -U bit_health_user -d bit_health_db -c "{sql_commands}"'

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD)
    print("Connected to remote server.")

    print(f"Executing SQL command...")
    stdin, stdout, stderr = ssh.exec_command(command)
    
    print("--- STDOUT ---")
    print(stdout.read().decode())
    
    print("--- STDERR ---")
    print(stderr.read().decode())

    ssh.close()
except Exception as e:
    print(f"Error executing command: {e}")
    sys.exit(1)
