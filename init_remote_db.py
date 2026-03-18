import paramiko

# Configuration
HOST = '59.10.164.2'
PORT = 22
USERNAME = 'bitcom'
PASSWORD = 'bitcom1983!'

def init_remote_db():
    ssh = None
    try:
        print(f"Connecting to {HOST}...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD)
        print("Connected.")

        # Use python -m to run as module so imports work
        cmd = "cd /home/bitcom/bit_health && docker compose exec -T backend python -m app.initial_data"
        
        print(f"Executing: {cmd}")
        stdin, stdout, stderr = ssh.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        
        if out: print(out)
        if err: print(f"Stderr: {err}")
        
        if exit_status == 0:
            print("Database initialized successfully!")
        else:
            print(f"Failed to initialize database. Exit code: {exit_status}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if ssh:
            ssh.close()

if __name__ == "__main__":
    init_remote_db()
