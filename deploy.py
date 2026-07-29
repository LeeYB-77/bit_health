import paramiko
import os
import sys
import tarfile

# Configuration (접속 정보는 .env에서 읽는다. remote_config 참조)
from remote_config import HOST, PORT, USERNAME, PASSWORD

REMOTE_PATH = '/home/bitcom/bit_health'
LOCAL_PATH = os.getcwd()


def safe_print(text):
    """Windows 콘솔(cp949)이 인코딩 못하는 문자(빌드 출력의 ✓ 등)로 인해
    배포가 실제로는 성공했는데도 print()에서 죽어 실패한 것처럼 보이는 문제를 막는다."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        print(text.encode(enc, errors="replace").decode(enc, errors="replace"))

def create_tarball(source_dir, output_filename):
    print(f"Creating tarball from {source_dir}...")
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir), filter=exclude_files)
    print("Tarball created.")

def exclude_files(tarinfo):
    exclude_patterns = ['node_modules', '.venv', 'venv', '__pycache__', '.git', '.next', 'dist', 'build', '.idea', '.vscode']
    for pattern in exclude_patterns:
        if pattern in tarinfo.name:
            return None
    return tarinfo

def deploy():
    ssh = None
    try:
        # 1. Create Tarball
        create_tarball(LOCAL_PATH, "project.tar.gz")

        # 2. Connect SSH
        print(f"Connecting to {HOST}...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(HOST, port=PORT, username=USERNAME, password=PASSWORD)
        print("Connected.")

        # 3. Upload File via SFTP
        print("Uploading project.tar.gz...")
        sftp = ssh.open_sftp()
        sftp.put("project.tar.gz", "/home/bitcom/project.tar.gz")
        sftp.close()
        print("Upload complete.")

        # 4. Execute Remote Commands
        # 'docker compose down'을 미리 하지 않는다 — 빌드가 실패하면 기존 컨테이너가
        # 이미 내려간 채로 아무것도 못 띄우는 사고가 난다(실제로 겪었다: 빌드 캐시
        # 스냅샷 오류로 backend 이미지 빌드가 실패했는데, down을 먼저 해버려서
        # 재시도 전까지 운영 사이트가 통째로 죽어 있었다). 'up -d --build'만으로도
        # 바뀐 컨테이너만 새로 띄우고, 빌드가 실패하면 기존 컨테이너는 그대로
        # 떠 있어 서비스가 끊기지 않는다.
        commands = [
            # Prepare directory
            f"mkdir -p {REMOTE_PATH}",

            # Extract (stripping top level folder to ensure it goes into bit_health exactly)
            f"tar -xzf /home/bitcom/project.tar.gz -C {REMOTE_PATH} --strip-components=1",

            # Clean up tar
            f"rm /home/bitcom/project.tar.gz",

            # Rename deploy_docker_compose.yml to docker-compose.yml to ensure it's used
            f"mv {REMOTE_PATH}/deploy_docker_compose.yml {REMOTE_PATH}/docker-compose.yml",

            # Restart Docker Compose (using 'docker compose' plugin style)
            f"cd {REMOTE_PATH} && docker compose up -d --build",
        ]

        failed = False
        for cmd in commands:
            print(f"Executing: {cmd}")
            stdin, stdout, stderr = ssh.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()

            if out: safe_print(out)
            if err: safe_print(f"Stderr: {err}")

            if exit_status != 0:
                print(f"Command failed with status {exit_status}")
                failed = True

        if failed:
            print(
                "\n[DEPLOYMENT FAILED] 위 명령 중 실패한 게 있습니다. "
                "'docker compose up -d --build'가 실패했다면 기존 컨테이너는 계속 떠 있으니 "
                "서비스 자체는 끊기지 않았을 가능성이 높지만, 새 코드는 반영되지 않았습니다. "
                "원격 서버에서 컨테이너 상태와 빌드 로그를 확인한 뒤 다시 실행해 주세요."
            )
        else:
            print("Deployment finished successfully!")

    except Exception as e:
        print(f"Deployment failed: {e}")
    finally:
        if ssh:
            ssh.close()
        if os.path.exists("project.tar.gz"):
            os.remove("project.tar.gz")

if __name__ == "__main__":
    deploy()
