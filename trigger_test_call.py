import urllib.request
import json
import time

auth_id = "MA_UX68R8GL"
auth_token = "SpqcgHeWozfLF58ifxDTRD4ueBx2cwifWGfiAVq4uQGIxHkXctQUbA4tmMpUOxgx"
from_num = "918065481653"
to_num = "+919731614215"
base_url = "https://89.116.122.41.nip.io"
camp_id = f"manual_data_edge_test_{int(time.time())}"

url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/Call/"
headers = {
    "X-Auth-ID": auth_id,
    "X-Auth-Token": auth_token,
    "Content-Type": "application/json",
}

body = {
    "from": from_num,
    "to": to_num,
    "answer_url": f"{base_url}/vobiz/answer?camp_id={camp_id}",
    "answer_method": "POST",
    "ring_url": f"{base_url}/vobiz/ring?camp_id={camp_id}",
    "ring_method": "POST",
    "hangup_url": f"{base_url}/vobiz/hangup?camp_id={camp_id}",
    "hangup_method": "POST",
    "hangup_on_ring": "60",
    "time_limit": 3600,
}

print(f"Triggering call to {to_num} from {from_num} via Vobiz API...")
req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'), headers=headers, method='POST')
try:
    with urllib.request.urlopen(req) as resp:
        res = resp.read().decode('utf-8')
        print("✅ VOBIZ API RESPONSE:", res)
except Exception as e:
    print("❌ CALL FAILED:", e)
