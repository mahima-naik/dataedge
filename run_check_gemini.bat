@echo off
cd /d "%~dp0"
echo ========================================================
echo Testing Gemini API & Live WebSocket Connection
echo ========================================================
python check_gemini.py
echo ========================================================
pause
