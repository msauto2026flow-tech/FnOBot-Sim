@echo off
title Nifty FnO Bot v5 — Morning Setup
color 0A
cls

echo ============================================================
echo   Nifty FnO Bot — v5  ^|  Germany Edition
echo ============================================================
echo.
echo   DAILY SCHEDULE
echo   04:30 Germany  =  09:00 IST  Pre-market briefing
echo   04:45 Germany  =  09:15 IST  Live scanning begins
echo   10:55 Germany  =  15:25 IST  EOD snapshot
echo   11:00 Germany  =  15:30 IST  Market closes
echo   07:30 PM Germany = Midnight IST  Token expires
echo ============================================================
echo.

cd /d %~dp0\..

echo Checking Kite token...
python scripts\check_token.py > %TEMP%\kite_check.txt 2>&1

findstr /C:"TOKEN_VALID" %TEMP%\kite_check.txt > nul
if %errorlevel% == 0 (
    echo [OK] Token is valid.
    echo.
) else (
    echo [!] Token expired — starting login...
    echo.
    python main.py --login
    echo.
)

echo Starting bot...
echo Press Ctrl+C to stop.
echo.
python main.py

echo.
echo ============================================================
echo   Bot stopped.
echo ============================================================
pause
