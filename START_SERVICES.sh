#!/bin/bash

# Start script for Vehicle Intelligence Platform
# This script starts all three services automatically

set -e

echo "================================================"
echo "  Vehicle Intelligence Platform - Starting Up"
echo "================================================"
echo ""

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# PIDs for cleanup
BACKEND_PID=""
ML_PID=""
FRONTEND_PID=""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Stopping all services..."
    [ -n "$BACKEND_PID" ] && kill $BACKEND_PID 2>/dev/null
    [ -n "$ML_PID" ] && kill $ML_PID 2>/dev/null
    [ -n "$FRONTEND_PID" ] && kill $FRONTEND_PID 2>/dev/null
    # Also kill any child processes
    jobs -p | xargs -r kill 2>/dev/null
    exit
}

trap cleanup SIGINT SIGTERM EXIT

# Function to kill process on port
kill_port() {
    local port=$1
    local pid=$(lsof -ti:$port 2>/dev/null)
    if [ ! -z "$pid" ]; then
        echo "  Killing existing process on port $port (PID: $pid)..."
        kill -9 $pid 2>/dev/null
        sleep 1
    fi
}

# Function to wait for a service to be ready
wait_for_service() {
    local url=$1
    local name=$2
    local max_attempts=${3:-30}
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo "  ✓ $name is ready"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    echo "  ✗ $name failed to start after ${max_attempts}s"
    return 1
}

# Kill any existing processes on our ports
echo "[1/6] Clearing ports..."
kill_port 3000
kill_port 3001
kill_port 8000

# ------------------------------------------
# Backend setup
# ------------------------------------------
echo "[2/6] Setting up Backend..."
cd "$SCRIPT_DIR/backend"
if [ ! -d "node_modules" ] || [ ! -d "node_modules/helmet" ]; then
    echo "  Installing backend dependencies..."
    npm install
fi

# ------------------------------------------
# Frontend setup
# ------------------------------------------
echo "[3/6] Setting up Frontend..."
cd "$SCRIPT_DIR/frontend"
if [ ! -d "node_modules" ] || [ ! -d "node_modules/next" ]; then
    echo "  Installing frontend dependencies..."
    npm install
fi

# ------------------------------------------
# ML Service setup
# ------------------------------------------
echo "[4/6] Setting up ML Service..."
cd "$SCRIPT_DIR/ml-service"

# Auto-create virtual environment if missing
if [ ! -d "venv" ]; then
    echo "  Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Auto-install/update dependencies
if [ ! -f "venv/.deps_installed" ] || [ "requirements.txt" -nt "venv/.deps_installed" ]; then
    echo "  Installing Python dependencies (this may take a while on first run)..."
    pip install --upgrade pip > /dev/null 2>&1
    pip install -r requirements.txt
    touch venv/.deps_installed
fi

# ------------------------------------------
# Start all services
# ------------------------------------------
echo "[5/6] Starting services..."

# Start Backend
echo "  Starting Backend API (port 3001)..."
cd "$SCRIPT_DIR/backend"
npm run dev > /tmp/vi-backend.log 2>&1 &
BACKEND_PID=$!

# Start ML Service
echo "  Starting ML Service (port 8000)..."
cd "$SCRIPT_DIR/ml-service"
source venv/bin/activate
export PYTHONPATH="$SCRIPT_DIR/ml-service:$PYTHONPATH"
python src/main.py > /tmp/vi-ml-service.log 2>&1 &
ML_PID=$!

# Start Frontend
echo "  Starting Frontend (port 3000)..."
cd "$SCRIPT_DIR/frontend"
npm run dev > /tmp/vi-frontend.log 2>&1 &
FRONTEND_PID=$!

# ------------------------------------------
# Verify all services are running
# ------------------------------------------
echo "[6/6] Waiting for services to be ready..."

# Check processes are still alive
sleep 3
FAILED=false

if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "  ✗ Backend failed to start. Logs:"
    tail -20 /tmp/vi-backend.log 2>/dev/null
    FAILED=true
fi

if ! kill -0 $ML_PID 2>/dev/null; then
    echo "  ✗ ML Service failed to start. Logs:"
    tail -20 /tmp/vi-ml-service.log 2>/dev/null
    FAILED=true
fi

if ! kill -0 $FRONTEND_PID 2>/dev/null; then
    echo "  ✗ Frontend failed to start. Logs:"
    tail -20 /tmp/vi-frontend.log 2>/dev/null
    FAILED=true
fi

if [ "$FAILED" = true ]; then
    echo ""
    echo "Some services failed to start. Check logs above."
    echo "  Backend log:    /tmp/vi-backend.log"
    echo "  ML Service log: /tmp/vi-ml-service.log"
    echo "  Frontend log:   /tmp/vi-frontend.log"
    # Don't exit — keep running services that did start
fi

# Wait for HTTP endpoints
wait_for_service "http://localhost:3001/api/jobs/health-check" "Backend" 15 || true
wait_for_service "http://localhost:8000/health" "ML Service" 15 || true
wait_for_service "http://localhost:3000" "Frontend" 30 || true

echo ""
echo "================================================"
echo "  All services started!"
echo "================================================"
echo ""
echo "  Frontend:   http://localhost:3000"
echo "  Backend:    http://localhost:3001"
echo "  ML Service: http://localhost:8000"
echo ""
echo "  Logs:"
echo "    Backend:    tail -f /tmp/vi-backend.log"
echo "    ML Service: tail -f /tmp/vi-ml-service.log"
echo "    Frontend:   tail -f /tmp/vi-frontend.log"
echo ""
echo "  Press Ctrl+C to stop all services"
echo ""

# Reset trap to not print cleanup on normal wait
trap cleanup SIGINT SIGTERM

# Wait for all processes
wait
