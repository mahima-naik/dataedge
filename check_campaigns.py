import requests

roles = ["buyers", "sellers", "rfqs", "data_edge", "real_estate", "factory", "vernikaai", "admin"]
running_campaigns = []

for role in roles:
    try:
        resp = requests.get("http://127.0.0.1:8001/api/campaign/state", headers={"X-User-Role": role})
        if resp.status_code == 200:
            data = resp.json()
            if data.get("active"):
                running_campaigns.append(role)
    except Exception as e:
        print(f"Error checking {role}: {e}")

print("Running campaigns:", running_campaigns)
