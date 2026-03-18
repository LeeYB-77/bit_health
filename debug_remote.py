import paramiko
import time

# Configuration
HOST = '59.10.164.2'
PORT = 22
USERNAME = 'bitcom'
PASSWORD = 'bitcom1983!'

def debug_remote():
    ssh = None
    try:
        print(f"Connecting to {HOST}...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD)
        print("Connected.")

        commands = [
            "echo '--- Docker Containers ---'",
            "docker ps",
            "echo '--- Backend Logs (Last 20) ---'",
            "cd /home/bitcom/bit_health && docker compose logs --tail=20 backend",
            "echo '--- Testing Backend Internally ---'",
            "curl -I http://localhost:8002/docs",
            "echo '--- Frontend Environment Check (Inspect Container) ---'",
            "docker inspect bit_health_frontend | grep NEXT_PUBLIC_API_URL"
        ]

        for cmd in commands:
            print(f"\n[Executing]: {cmd}")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            # Wait a bit for output
            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            
            if out: print(out)
            if err: print(f"STDERR: {err}")

    except Exception as e:
        print(f"Debug failed: {e}")
    finally:
        if ssh:
            ssh.close()

if __name__ == "__main__":
    debug_remote()
