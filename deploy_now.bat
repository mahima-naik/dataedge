@echo off
cd /d "%~dp0"
echo ========================================================
echo Pushing updated backend & call scripts to VPS 89.116.122.41
echo ========================================================
scp .env backend\config.py backend\diagnose_calls.py root@89.116.122.41:/root/vernika/backend/
scp backend\api\routes\vobiz.py root@89.116.122.41:/root/vernika/backend/api/routes/
scp backend\services\vobiz_bridge\live_session.py backend\services\vobiz_bridge\gemini_protocol.py backend\services\vobiz_bridge\turn_taking_addon.py root@89.116.122.41:/root/vernika/backend/services/vobiz_bridge/
scp backend\prompts\priya.py root@89.116.122.41:/root/vernika/backend/prompts/
scp backend\scripts\call_number.py root@89.116.122.41:/root/vernika/backend/scripts/
echo.
echo Restarting dataedge.service on VPS...
ssh root@89.116.122.41 "systemctl restart dataedge.service || systemctl restart vernika.service"
echo.
echo ========================================================
echo SUCCESS: VPS 89.116.122.41 updated and restarted!
echo ========================================================
pause
