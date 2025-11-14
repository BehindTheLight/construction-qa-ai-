#!/bin/bash

# ==============================================================================
# AI-QA-PG Setup Script for macOS/Linux
# ==============================================================================
# This script automates the installation and setup of the AI-QA-PG project.
# It will install all dependencies, configure the environment, and prepare
# the system for first run.
# ==============================================================================

set -e  # Exit on error

echo "================================================================================"
echo "                    AI-QA-PG Automated Setup (macOS/Linux)"
echo "================================================================================"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# ==============================================================================
# Step 1: Check Prerequisites
# ==============================================================================
echo "Step 1: Checking prerequisites..."
echo ""

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    echo -e "${GREEN}✓${NC} Python 3 found: $PYTHON_VERSION"
else
    echo -e "${RED}✗${NC} Python 3 is not installed"
    echo "Please install Python 3.11 or higher from https://www.python.org/"
    exit 1
fi

# Check Node.js
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo -e "${GREEN}✓${NC} Node.js found: $NODE_VERSION"
else
    echo -e "${RED}✗${NC} Node.js is not installed"
    echo "Please install Node.js 18+ from https://nodejs.org/"
    exit 1
fi

# Check PostgreSQL
if command -v psql &> /dev/null || command -v postgres &> /dev/null; then
    echo -e "${GREEN}✓${NC} PostgreSQL found"
else
    echo -e "${YELLOW}⚠${NC} PostgreSQL not found. You'll need to install it:"
    echo "  macOS: brew install postgresql@15"
    echo "  Linux: sudo apt install postgresql-15"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check OpenSearch (optional - can use Docker)
if curl -s http://localhost:9200 > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} OpenSearch is running"
else
    echo -e "${YELLOW}⚠${NC} OpenSearch not detected on localhost:9200"
    echo "You can either:"
    echo "  1. Install OpenSearch locally"
    echo "  2. Use Docker: docker run -d -p 9200:9200 -e 'discovery.type=single-node' opensearchproject/opensearch:2.11.0"
    echo "  3. Use docker-compose from infra/ directory"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""

# ==============================================================================
# Step 2: Setup Environment Variables
# ==============================================================================
echo "Step 2: Setting up environment variables..."
echo ""

if [ ! -f "infra/.env" ]; then
    if [ -f "infra/.env.example" ]; then
        cp infra/.env.example infra/.env
        echo -e "${GREEN}✓${NC} Created infra/.env from template"
        echo ""
        echo -e "${YELLOW}IMPORTANT:${NC} Please edit infra/.env and add your API keys:"
        echo "  - NAGA_API_KEY (required)"
        echo "  - COHERE_API_KEY (required for reranking)"
        echo "  - POSTGRES_DSN (update with your database credentials)"
        echo ""
        read -p "Press Enter after you've updated infra/.env with your API keys..."
    else
        echo -e "${RED}✗${NC} infra/.env.example not found"
        exit 1
    fi
else
    echo -e "${GREEN}✓${NC} infra/.env already exists"
fi

echo ""

# ==============================================================================
# Step 3: Install Backend Dependencies
# ==============================================================================
echo "Step 3: Installing backend dependencies..."
echo ""

cd api

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
    echo -e "${GREEN}✓${NC} Virtual environment created"
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

echo -e "${GREEN}✓${NC} Backend dependencies installed"
echo ""

cd ..

# ==============================================================================
# Step 4: Install Frontend Dependencies
# ==============================================================================
echo "Step 4: Installing frontend dependencies..."
echo ""

cd app

echo "Installing Node.js packages..."
npm install

echo -e "${GREEN}✓${NC} Frontend dependencies installed"
echo ""

cd ..

# ==============================================================================
# Step 5: Create Data Directories
# ==============================================================================
echo "Step 5: Creating data directories..."
echo ""

mkdir -p data/uploads
mkdir -p data/extracts

echo -e "${GREEN}✓${NC} Data directories created"
echo ""

# ==============================================================================
# Step 6: Initialize Database
# ==============================================================================
echo "Step 6: Database setup..."
echo ""

echo "Checking PostgreSQL connection..."
# Source the .env file to get POSTGRES_DSN
set -a
source infra/.env
set +a

# Try to connect to PostgreSQL
if psql "$POSTGRES_DSN" -c '\q' 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Database connection successful"
    
    # Check if schema file exists
    if [ -f "api/db/schema.sql" ]; then
        echo "Do you want to initialize the database schema?"
        read -p "(y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            psql "$POSTGRES_DSN" < api/db/schema.sql
            echo -e "${GREEN}✓${NC} Database schema initialized"
        fi
    fi
else
    echo -e "${YELLOW}⚠${NC} Could not connect to database"
    echo "Please ensure PostgreSQL is running and POSTGRES_DSN in infra/.env is correct"
fi

echo ""

# ==============================================================================
# Step 7: Initialize OpenSearch Indices
# ==============================================================================
echo "Step 7: OpenSearch index setup..."
echo ""

if curl -s http://localhost:9200 > /dev/null 2>&1; then
    echo "Initializing OpenSearch indices..."
    cd api
    source venv/bin/activate
    
    if [ -f "search/create_index.py" ]; then
        python search/create_index.py 2>/dev/null || echo -e "${YELLOW}⚠${NC} Index may already exist"
    fi
    
    if [ -f "search/create_table_index.py" ]; then
        python search/create_table_index.py 2>/dev/null || echo -e "${YELLOW}⚠${NC} Table index may already exist"
    fi
    
    echo -e "${GREEN}✓${NC} OpenSearch indices initialized"
    cd ..
else
    echo -e "${YELLOW}⚠${NC} OpenSearch not running, skipping index creation"
    echo "You'll need to create indices manually later"
fi

echo ""

# ==============================================================================
# Step 8: Install System Dependencies (Tesseract for OCR)
# ==============================================================================
echo "Step 8: Checking system dependencies..."
echo ""

if command -v tesseract &> /dev/null; then
    echo -e "${GREEN}✓${NC} Tesseract OCR found"
else
    echo -e "${YELLOW}⚠${NC} Tesseract OCR not found (needed for scanned PDFs)"
    echo "Install with:"
    echo "  macOS: brew install tesseract"
    echo "  Linux: sudo apt install tesseract-ocr"
fi

echo ""

# ==============================================================================
# Step 9: Create Start Scripts
# ==============================================================================
echo "Step 9: Creating start scripts..."
echo ""

# Create start script
cat > start.sh << 'EOF'
#!/bin/bash

# Start AI-QA-PG Application

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "================================================================================"
echo "                    Starting AI-QA-PG Application"
echo "================================================================================"
echo ""

# Check if services are running
if ! curl -s http://localhost:9200 > /dev/null 2>&1; then
    echo "WARNING: OpenSearch is not running on localhost:9200"
    echo "Start it with: docker run -d -p 9200:9200 -e 'discovery.type=single-node' opensearchproject/opensearch:2.11.0"
    echo ""
fi

# Start backend
echo "Starting Backend API on http://localhost:8000"
cd api
source venv/bin/activate
unset LLM_MODEL LLM_PROVIDER LLM_BASE_URL
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

sleep 3

# Start frontend
echo "Starting Frontend on http://localhost:3000"
cd app
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "================================================================================"
echo "Application started successfully!"
echo ""
echo "Backend API:  http://localhost:8000"
echo "API Docs:     http://localhost:8000/docs"
echo "Frontend:     http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services"
echo "================================================================================"
echo ""

# Wait for Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

wait
EOF

chmod +x start.sh

echo -e "${GREEN}✓${NC} Start script created (./start.sh)"
echo ""

# ==============================================================================
# Setup Complete
# ==============================================================================
echo "================================================================================"
echo -e "${GREEN}                    Setup Complete!${NC}"
echo "================================================================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Verify your API keys in infra/.env:"
echo "   - NAGA_API_KEY"
echo "   - COHERE_API_KEY"
echo "   - POSTGRES_DSN"
echo ""
echo "2. Ensure services are running:"
echo "   - PostgreSQL"
echo "   - OpenSearch (or use Docker)"
echo ""
echo "3. Start the application:"
echo "   ./start.sh"
echo ""
echo "4. Open your browser:"
echo "   http://localhost:3000"
echo ""
echo "================================================================================"
echo ""

