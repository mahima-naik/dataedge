#!/usr/bin/env python3
"""Login and trigger manual call - runs on VPS."""
import json
import urllib.request
import sys

LOCAL = "http://localhost:8001"
phone = sys.argv[1] if len(sys.argv) > 1 else "9731614215"
callee_name = sys.argv[2] if len(sys.argv) > 2 else "Test User"

# Step 1: Login
print(f"[1/2] Logging in...")
login_payload = json.dumps({"email": "dataedge@pitchxai.com", "password": "DataEdge@123"}).encode()
login_req = urllib.request.Request(
    f"{LOCAL}/api/login",
    data=login_payload,
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(login_req, timeout=15) as resp:
        login_data = json.loads(resp.read().decode())
        token = login_data["token"]
        print(f"  Login OK (role={login_data['role']})")
except Exception as e:
    print(f"  Login failed: {e}")
    sys.exit(1)

# Step 2: Trigger call
print(f"[2/2] Triggering call to {phone}...")
call_payload = json.dumps({"to": phone, "callee_name": callee_name}).encode()
call_req = urllib.request.Request(
    f"{LOCAL}/api/manual/call",
    data=call_payload,
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
)

try:
    with urllib.request.urlopen(call_req, timeout=30) as resp:
        call_data = json.loads(resp.read().decode())
        print(f"  Call triggered: {json.dumps(call_data, indent=2)}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"  HTTP {e.code}: {body}")
except Exception as e:
    print(f"  Error: {e}")
