"""上传前端文件 + 重启"""
import paramiko, io, sys, time, os
from scp import SCPClient
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("106.13.186.155", port=6078, username="Developer", password="rS6HJ4", timeout=10)
PROJ = "/home/Developer/library-ai-guide"
SRC = r"C:\Users\Administrator\Desktop\Hackathon"

with SCPClient(ssh.get_transport()) as scp:
    scp.put(os.path.join(SRC, "frontend/index.html"), f"{PROJ}/frontend/index.html")
    scp.put(os.path.join(SRC, "frontend/js/camera.js"), f"{PROJ}/frontend/js/camera.js")
print("[1] Uploaded frontend")

ssh.exec_command("pkill -9 -f uvicorn 2>/dev/null", timeout=5)
time.sleep(2)
ssh.exec_command("fuser -k 7000/tcp 2>/dev/null", timeout=5)
time.sleep(1)
ch = ssh.get_transport().open_session()
ch.exec_command(
    f"cd {PROJ} && source venv/bin/activate && "
    "nohup uvicorn backend.main:app --host 0.0.0.0 --port 7000 > server.log 2>&1 &"
)
ch.close()
time.sleep(8)

stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:7000/health 2>&1", timeout=10)
print(f"[2] Health: {stdout.read().decode('utf-8', '')[:100]}")

stdin, stdout, stderr = ssh.exec_command(f"grep -c 'imageFileInput' {PROJ}/frontend/index.html", timeout=5)
print(f"[3] File input: {stdout.read().decode('utf-8', '').strip()} matches")

ssh.close()
print("\nDone! http://106.13.186.155:7078")
