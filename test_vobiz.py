import httpx
import asyncio

async def test():
    auth_id = "MA_8HLLO728"
    auth_token = "DGOxQpiivBkkIPgY6J1zM010xkCc5iOGVpEJzFOYXnY8iSPYFECalRa3IjRZzwA1"
    url = f"https://api.vobiz.ai/api/v1/Account/{auth_id}/"
    headers = {
        "X-Auth-ID": auth_id,
        "X-Auth-Token": auth_token,
    }
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=headers)
        print(r.status_code, r.text)

asyncio.run(test())
