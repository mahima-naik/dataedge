import asyncio
from backend.core.auth import dashboard_role_for_token
print(dashboard_role_for_token("realestate@procucev.com", "real_estate"))
