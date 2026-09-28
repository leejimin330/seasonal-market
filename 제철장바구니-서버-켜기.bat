@echo off
chcp 65001 >nul
title 제철 장바구니 실행기

set "PROJ=C:\Users\lapla\seasonal-market"
set "PY=C:\Users\lapla\seasonal-market\.venv\Scripts\python.exe"

echo ============================================
echo  제철 장바구니 - 웹서버 실행 (포트 8741)
echo ============================================
echo.

cd /d "%PROJ%"

REM 이미 떠 있는 8741 서버를 먼저 정리한다. 둘이 같은 포트를 잡으면 둘 다 실패한다.
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like '%%python%%'\" | Where-Object { $_.CommandLine -like '*uvicorn*8741*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [1/2] 웹서버를 새 창에서 시작합니다...
start "제철 장바구니 서버 (8741)" /D "%PROJ%" "%PY%" -m uvicorn --factory app.main:build_default_app --host 127.0.0.1 --port 8741

echo [2/2] 서버가 뜨면 브라우저를 엽니다...
powershell -NoProfile -Command "1..30 | ForEach-Object { try { Invoke-WebRequest -Uri 'http://127.0.0.1:8741/api/status' -TimeoutSec 2 -UseBasicParsing | Out-Null; exit 0 } catch { Start-Sleep 1 } }"
start "" http://127.0.0.1:8741/

echo.
echo 끄려면 "제철 장바구니 서버" 창을 닫으세요.
timeout /t 5 >nul
