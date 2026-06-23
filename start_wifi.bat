@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate
echo Installing requirements...
pip install -r requirements.txt
cls
echo ================================================
echo IlmStart EDU Wi-Fi start
echo ================================================
echo.
echo 1) Keep laptop and phone on the same Wi-Fi.
echo 2) On the phone open: http://YOUR-IP:5000
echo 3) Your IPv4 addresses are shown below:
echo.
ipconfig | findstr /i "IPv4"
echo.
echo If phone does not open the site, allow Python in Windows Firewall.
echo.
python app.py
pause
