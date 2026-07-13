"""推送到 GitHub - 清理版"""
import os, shutil, subprocess
from pathlib import Path

ROOT = Path(r"C:\Users\Administrator\Desktop\Hackathon")
TEMP = ROOT / "_push_temp"
REPO = "https://github.com/finalyb/Multi-Agent-Library-Guide-System.git"

# Step 1: Remove old temp completely
print("[1] Clean old temp...")
if TEMP.exists():
    shutil.rmtree(str(TEMP), ignore_errors=True)

# Step 2: Fresh clone
print("[2] Clone...")
r = subprocess.run(["git", "clone", REPO, str(TEMP)], capture_output=True, text=True, cwd=str(ROOT))
print(r.stderr.strip())

# Step 3: Delete old content (keep .git)
print("[3] Remove old files...")
for item in list(TEMP.iterdir()):
    if item.name != ".git":
        if item.is_dir():
            shutil.rmtree(str(item), ignore_errors=True)
        else:
            item.unlink(missing_ok=True)

# Step 4: Copy new files
print("[4] Copy files...")
EXCLUDE = [
    "_push_temp", "_temp_repo", ".git", ".claude", ".recall",
    ".env", "__pycache__", "wheels", "llama_src.tar.gz",
    "jxt-deploy.tar.gz", ".xlsx", "data\\chroma_db", "\\chroma_db",
]

copied = 0
for f in ROOT.rglob("*"):
    rel_str = str(f.relative_to(ROOT))
    if any(x in rel_str for x in EXCLUDE):
        continue
    if f.is_file() and not f.name.startswith("."):
        dest = TEMP / rel_str
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(f), str(dest))
        copied += 1
print(f"  Copied {copied} files")

# Step 5: Git add + commit
print("[5] Git add + commit...")
os.chdir(str(TEMP))
subprocess.run(["git", "config", "user.email", "yangbo@bgu.edu.cn"])
subprocess.run(["git", "config", "user.name", "finalyb"])
subprocess.run(["git", "add", "-A"])
r = subprocess.run(["git", "status", "--short"], capture_output=True, text=True)
changes = len(r.stdout.strip().split("\n")) if r.stdout.strip() else 0
print(f"  Changes: {changes} files")

r = subprocess.run(
    ["git", "commit", "-m", "v2.0: Clean sensitive data, optimize README, add deployment docs"],
    capture_output=True, text=True,
)
print(f"  Commit: {r.stdout.strip()[-100:]}")

# Step 6: Push
print("[6] Push...")
r = subprocess.run(
    ["git", "push", "origin", "main"],
    capture_output=True, text=True,
    timeout=120,
)
print(r.stdout.strip()[-200:])
if r.stderr.strip():
    print("  stderr:", r.stderr.strip()[-200:])

if r.returncode == 0:
    print("\n*** PUSH SUCCESS! ***")
else:
    print(f"\nPush failed with code {r.returncode}")

# Clean
os.chdir(str(ROOT))
