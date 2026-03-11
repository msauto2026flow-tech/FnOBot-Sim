@echo off
title EOD Data Fetcher
color 0B
cls

echo ============================================================
echo   EOD Data Fetcher  --  Kite Connect
echo   Fetches NIFTY + BANKNIFTY option chain + Nifty 50 stocks
echo ============================================================
echo.
echo   Run AFTER 3:30 PM IST for complete EOD data.
echo.

cd /d C:\Users\marut\Desktop\FnOBot

echo   Date format must be: YYYY-MM-DD  (example: 2026-03-06)
echo.
set /p DATE="Enter date or press Enter for TODAY: "

if "%DATE%"=="" (
    echo Fetching TODAY's EOD data...
    python eod_data_fetcher.py
) else (
    echo Fetching EOD data for %DATE%...
    python eod_data_fetcher.py %DATE%
)

echo.
pause