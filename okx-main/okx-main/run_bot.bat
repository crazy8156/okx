@echo off
echo Starting OKX Trading Bot...
cd /d "%~dp0"
echo Current Directory: %CD%
uvicorn okx_bot.server:app --reload
pause
