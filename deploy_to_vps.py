import os
import subprocess
import sys

print("========================================================")
print("Deploying updated live_session.py & backend to 89.116.122.41")
print("========================================================")

# Detect which directory exists on the VPS, default to /root/vernika
print("Detecting remote directory on VPS...")
import subprocess

# We will try to create the directories first
target_host = "root@89.116.122.41"
remote_dir = "/root/vernika"

# Check if /root/DataEdge exists instead
check_cmd = f'ssh {target_host} "test -d /root/DataEdge && echo yes || echo no"'
try:
    res = subprocess.check_output(check_cmd, shell=True).decode().strip()
    if res == "yes":
        remote_dir = "/root/DataEdge"
        print("Using remote directory: /root/DataEdge")
except Exception:
    pass

# Ensure target directories exist
print(f"Ensuring remote directories exist in {remote_dir}...")
mkdir_cmd = f'ssh {target_host} "mkdir -p {remote_dir}/backend/api/routes {remote_dir}/backend/services/vobiz_bridge {remote_dir}/backend/prompts {remote_dir}/backend/scripts"'
os.system(mkdir_cmd)

files_to_copy = [
    (".env", f"{remote_dir}/.env"),
    (".env", f"{remote_dir}/backend/.env"),
    ("backend/config.py", f"{remote_dir}/backend/config.py"),
    ("backend/diagnose_calls.py", f"{remote_dir}/backend/diagnose_calls.py"),
    ("backend/api/routes/vobiz.py", f"{remote_dir}/backend/api/routes/vobiz.py"),
    ("backend/services/vobiz_bridge/live_session.py", f"{remote_dir}/backend/services/vobiz_bridge/live_session.py"),
    ("backend/services/vobiz_bridge/gemini_protocol.py", f"{remote_dir}/backend/services/vobiz_bridge/gemini_protocol.py"),
    ("backend/services/vobiz_bridge/turn_taking_addon.py", f"{remote_dir}/backend/services/vobiz_bridge/turn_taking_addon.py"),
    ("backend/prompts/priya.py", f"{remote_dir}/backend/prompts/priya.py"),
    ("backend/scripts/call_number.py", f"{remote_dir}/backend/scripts/call_number.py"),
]

for src, dst in files_to_copy:
    if os.path.exists(src):
        cmd = f"scp {src} {target_host}:{dst}"
        print(f"SCP {src} -> {dst}")
        os.system(cmd)

print("\nRestarting service on VPS...")
os.system(f'ssh {target_host} "systemctl restart vernika.service || systemctl restart dataedge.service"')

print("\n========================================================")
print(f"SUCCESS: VPS {target_host} updated & restarted!")
print("========================================================")
