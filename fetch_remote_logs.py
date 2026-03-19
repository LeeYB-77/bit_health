import paramiko
import sys

HOST = '59.10.164.2'
PORT = 22
USERNAME = 'bitcom'
PASSWORD = 'bitcom1983!'

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD)
    print("Connected to remote server.")

    stdin, stdout, stderr = ssh.exec_command('docker logs --tail 50 bit_health_backend')
    
    print("--- STDOUT ---")
    print(stdout.read().decode())
    
    print("--- STDERR ---")
    print(stderr.read().decode())

    ssh.close()
except Exception as e:
    print(f"Error fetching logs: {e}")
    sys.exit(1)
