@echo off
setlocal
cd /d "%~dp0"

echo Tender Sathi - Windows setup and launch
if not exist ".venv\Scripts\python.exe" (
    echo Creating the virtual environment...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo The Python launcher was not found. Try: python -m venv .venv
        exit /b 1
    )
)

.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

if "%DATABASE_URL%"=="" (
    echo WARNING: DATABASE_URL is not set in this Command Prompt window.
    echo Set PostgreSQL configuration before using the dashboard, for example:
    echo set DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/tender_sathi
)
if "%SECRET_KEY%"=="" set SECRET_KEY=local-development-secret
if "%APP_BASE_URL%"=="" set APP_BASE_URL=http://127.0.0.1:8000

.venv\Scripts\python.exe -m uvicorn app:app --reload
