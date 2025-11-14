@echo off
REM ==============================================================================
REM AI-QA-PG Setup Script for Windows
REM ==============================================================================
REM This script automates the installation and setup of the AI-QA-PG project.
REM It will install all dependencies, configure the environment, and prepare
REM the system for first run.
REM ==============================================================================

setlocal enabledelayedexpansion

echo ================================================================================
echo                     AI-QA-PG Automated Setup (Windows)
echo ================================================================================
echo.

cd /d "%~dp0"

REM ==============================================================================
REM Step 1: Check Prerequisites
REM ==============================================================================
echo Step 1: Checking prerequisites...
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Python is not installed
    echo Please install Python 3.11 or higher from https://www.python.org/
    pause
    exit /b 1
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
    echo [√] Python found: !PYTHON_VERSION!
)

REM Check Node.js
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Node.js is not installed
    echo Please install Node.js 18+ from https://nodejs.org/
    pause
    exit /b 1
) else (
    for /f %%i in ('node --version') do set NODE_VERSION=%%i
    echo [√] Node.js found: !NODE_VERSION!
)

REM Check PostgreSQL
psql --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] PostgreSQL not found. You'll need to install it:
    echo     Download from: https://www.postgresql.org/download/windows/
    set /p CONTINUE="Continue anyway? (y/n): "
    if /i "!CONTINUE!" neq "y" exit /b 1
) else (
    echo [√] PostgreSQL found
)

REM Check OpenSearch
curl -s http://localhost:9200 >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] OpenSearch not detected on localhost:9200
    echo You can either:
    echo   1. Install OpenSearch locally
    echo   2. Use Docker Desktop with the provided docker-compose.yml
    set /p CONTINUE="Continue anyway? (y/n): "
    if /i "!CONTINUE!" neq "y" exit /b 1
) else (
    echo [√] OpenSearch is running
)

echo.

REM ==============================================================================
REM Step 2: Setup Environment Variables
REM ==============================================================================
echo Step 2: Setting up environment variables...
echo.

if not exist "infra\.env" (
    if exist "infra\.env.example" (
        copy "infra\.env.example" "infra\.env"
        echo [√] Created infra\.env from template
        echo.
        echo IMPORTANT: Please edit infra\.env and add your API keys:
        echo   - NAGA_API_KEY (required)
        echo   - COHERE_API_KEY (required for reranking)
        echo   - POSTGRES_DSN (update with your database credentials)
        echo.
        pause
    ) else (
        echo [X] infra\.env.example not found
        pause
        exit /b 1
    )
) else (
    echo [√] infra\.env already exists
)

echo.

REM ==============================================================================
REM Step 3: Install Backend Dependencies
REM ==============================================================================
echo Step 3: Installing backend dependencies...
echo.

cd api

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating Python virtual environment...
    python -m venv venv
    echo [√] Virtual environment created
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing Python packages...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo [√] Backend dependencies installed
echo.

cd ..

REM ==============================================================================
REM Step 4: Install Frontend Dependencies
REM ==============================================================================
echo Step 4: Installing frontend dependencies...
echo.

cd app

echo Installing Node.js packages...
call npm install

echo [√] Frontend dependencies installed
echo.

cd ..

REM ==============================================================================
REM Step 5: Create Data Directories
REM ==============================================================================
echo Step 5: Creating data directories...
echo.

if not exist "data\uploads" mkdir data\uploads
if not exist "data\extracts" mkdir data\extracts

echo [√] Data directories created
echo.

REM ==============================================================================
REM Step 6: Initialize Database
REM ==============================================================================
echo Step 6: Database setup...
echo.

echo Checking PostgreSQL connection...
REM Load environment variables from .env
for /f "tokens=1,2 delims==" %%a in (infra\.env) do (
    if "%%a"=="POSTGRES_DSN" set POSTGRES_DSN=%%b
)

REM Note: Automatic database initialization requires psql command-line tool
echo Please ensure PostgreSQL is running and manually run:
echo   psql "!POSTGRES_DSN!" ^< api\db\schema.sql
echo.

REM ==============================================================================
REM Step 7: Initialize OpenSearch Indices
REM ==============================================================================
echo Step 7: OpenSearch index setup...
echo.

curl -s http://localhost:9200 >nul 2>&1
if %errorlevel% equ 0 (
    echo Initializing OpenSearch indices...
    cd api
    call venv\Scripts\activate.bat
    
    if exist "search\create_index.py" (
        python search\create_index.py 2>nul
        if %errorlevel% neq 0 echo [!] Index may already exist
    )
    
    if exist "search\create_table_index.py" (
        python search\create_table_index.py 2>nul
        if %errorlevel% neq 0 echo [!] Table index may already exist
    )
    
    echo [√] OpenSearch indices initialized
    cd ..
) else (
    echo [!] OpenSearch not running, skipping index creation
    echo You'll need to create indices manually later
)

echo.

REM ==============================================================================
REM Step 8: Check System Dependencies
REM ==============================================================================
echo Step 8: Checking system dependencies...
echo.

tesseract --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Tesseract OCR not found (needed for scanned PDFs)
    echo Download from: https://github.com/UB-Mannheim/tesseract/wiki
) else (
    echo [√] Tesseract OCR found
)

echo.

REM ==============================================================================
REM Step 9: Create Start Scripts
REM ==============================================================================
echo Step 9: Creating start scripts...
echo.

REM Create start script
echo @echo off > start.bat
echo REM Start AI-QA-PG Application >> start.bat
echo. >> start.bat
echo echo ================================================================================ >> start.bat
echo echo                     Starting AI-QA-PG Application >> start.bat
echo echo ================================================================================ >> start.bat
echo echo. >> start.bat
echo. >> start.bat
echo REM Check if OpenSearch is running >> start.bat
echo curl -s http://localhost:9200 ^>nul 2^>^&1 >> start.bat
echo if %%errorlevel%% neq 0 ( >> start.bat
echo     echo WARNING: OpenSearch is not running on localhost:9200 >> start.bat
echo     echo Start it with Docker Desktop or install locally >> start.bat
echo     echo. >> start.bat
echo ^) >> start.bat
echo. >> start.bat
echo REM Start backend >> start.bat
echo echo Starting Backend API on http://localhost:8000 >> start.bat
echo cd api >> start.bat
echo call venv\Scripts\activate.bat >> start.bat
echo set LLM_MODEL= >> start.bat
echo set LLM_PROVIDER= >> start.bat
echo set LLM_BASE_URL= >> start.bat
echo start /B python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload >> start.bat
echo cd .. >> start.bat
echo. >> start.bat
echo timeout /t 3 /nobreak ^>nul >> start.bat
echo. >> start.bat
echo REM Start frontend >> start.bat
echo echo Starting Frontend on http://localhost:3000 >> start.bat
echo cd app >> start.bat
echo start /B npm run dev >> start.bat
echo cd .. >> start.bat
echo. >> start.bat
echo echo. >> start.bat
echo echo ================================================================================ >> start.bat
echo echo Application started successfully! >> start.bat
echo echo. >> start.bat
echo echo Backend API:  http://localhost:8000 >> start.bat
echo echo API Docs:     http://localhost:8000/docs >> start.bat
echo echo Frontend:     http://localhost:3000 >> start.bat
echo echo. >> start.bat
echo echo Press any key to stop all services >> start.bat
echo echo ================================================================================ >> start.bat
echo echo. >> start.bat
echo. >> start.bat
echo pause >> start.bat
echo. >> start.bat
echo REM Kill processes on exit >> start.bat
echo taskkill /F /IM python.exe /FI "WINDOWTITLE eq uvicorn*" 2^>nul >> start.bat
echo taskkill /F /IM node.exe /FI "WINDOWTITLE eq npm*" 2^>nul >> start.bat

echo [√] Start script created (start.bat)
echo.

REM ==============================================================================
REM Setup Complete
REM ==============================================================================
echo ================================================================================
echo                     Setup Complete!
echo ================================================================================
echo.
echo Next steps:
echo.
echo 1. Verify your API keys in infra\.env:
echo    - NAGA_API_KEY
echo    - COHERE_API_KEY
echo    - POSTGRES_DSN
echo.
echo 2. Ensure services are running:
echo    - PostgreSQL
echo    - OpenSearch (or use Docker Desktop)
echo.
echo 3. Initialize the database:
echo    psql "YOUR_POSTGRES_DSN" ^< api\db\schema.sql
echo.
echo 4. Start the application:
echo    start.bat
echo.
echo 5. Open your browser:
echo    http://localhost:3000
echo.
echo ================================================================================
echo.

pause

