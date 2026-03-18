import paramiko

# Configuration
HOST = '59.10.164.2'
PORT = 22
USERNAME = 'bitcom'
PASSWORD = 'bitcom1983!'

def check_status():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        print(f"Connecting to {HOST}...")
        ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD)
        print("Connected.")

        commands = [
            "docker ps -a",
            "docker logs bit_health_backend --tail 50"
        ]

        for cmd in commands:
            print(f"\n--- Executing: {cmd} ---")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            print(stdout.read().decode())
            print(stderr.read().decode())

    except Exception as e:
        print(f"Connection failed: {e}")
    finally:
        ssh.close()

if __name__ == "__main__":
    check_status()
