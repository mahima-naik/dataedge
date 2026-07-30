#!/usr/bin/env python3
"""Generate token and trigger call."""
import sys
sys.path.insert(0, "/root/app")
sys.path.insert(0, "/root/app/backend")

from core.auth import create_token
import json
import urllib.request

# Generate token
token_data = create_token("dataedge@pitchxai.com", "data_edge")
token = token_data["token"]
print(f"Token generated")

# Trigger call
phone = sys.argv[1] if len(sys.argv) > 1 else "9731614215"
name = sys.argv[2] if len(sys.argv) > 2 else "Test User"

payload = json.dumps({"to": phone, "callee_name": name}).encode()
req = urllib.request.Request(
    "http://localhost:8001/api/manual/call",
    data=payload,
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
        print(f"Call triggered: {json.dumps(data, indent=2)}")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode()}")
except Exception as e:
    print(f"Error: {e}")
