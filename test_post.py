import urllib.request, json, ssl

ctx = ssl.create_default_context()
data = json.dumps({"to": "+919731614215", "callee_name": "Test"}).encode()
req = urllib.request.Request(
    "https://89.116.122.41.nip.io/api/manual/call?role=data_edge",
    data=data,
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    resp = urllib.request.urlopen(req, context=ctx, timeout=10)
    print("STATUS:", resp.status)
    print("BODY:", resp.read().decode())
except urllib.error.HTTPError as e:
    print("ERROR:", e.code)
    print("BODY:", e.read().decode())
except Exception as e:
    print("EXCEPTION:", e)
