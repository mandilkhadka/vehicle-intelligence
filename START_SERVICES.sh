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

if [ -s "$HOME/.nvm/nvm.sh" ]; then
    # Ensure native Node dependencies, especially better-sqlite3, run on the
    # repo's supported Node version instead of a newer system Node.
    unset npm_config_prefix
    # shellcheck source=/dev/null
    . "$HOME/.nvm/nvm.sh"
    if [ -f "$SCRIPT_DIR/.nvmrc" ]; then
        nvm use --silent > /dev/null
    fi
fi

MIN_PYTHON_VERSION="3.10"

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

python_version() {
    "$1" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'
}

python_meets_min_version() {
    "$1" - "$MIN_PYTHON_VERSION" <<'PY'
import sys

required = tuple(int(part) for part in sys.argv[1].split("."))
raise SystemExit(0 if sys.version_info[:2] >= required else 1)
PY
}

find_python() {
    local candidates=()

    if [ -n "${PYTHON:-}" ]; then
        candidates+=("$PYTHON")
    fi

    candidates+=(python3.12 python3.11 python3.10 python3.13 python3)

    for candidate in "${candidates[@]}"; do
        if command -v "$candidate" >/dev/null 2>&1 && python_meets_min_version "$candidate"; then
            command -v "$candidate"
            return 0
        fi
    done

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

PYTHON_BIN="$(find_python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "  ✗ Python $MIN_PYTHON_VERSION+ is required for the ML service dependencies."
    echo "    Install Python $MIN_PYTHON_VERSION or newer, or set PYTHON=/path/to/python before running this script."
    exit 1
fi

if [ -x "venv/bin/python" ] && ! python_meets_min_version "venv/bin/python"; then
    echo "  Existing ML venv uses Python $(python_version "venv/bin/python"), but dependencies require $MIN_PYTHON_VERSION+."
    echo "  Recreating ML virtual environment with $("$PYTHON_BIN" --version 2>&1)..."
    rm -rf venv
fi

if [ -d "venv" ] && [ ! -x "venv/bin/python" ]; then
    echo "  Existing ML venv is incomplete. Recreating it..."
    rm -rf venv
fi

# Auto-create virtual environment if missing
if [ ! -d "venv" ]; then
    echo "  Creating Python virtual environment..."
    "$PYTHON_BIN" -m venv venv
fi

# Activate venv
source venv/bin/activate
VENV_PYTHON="$SCRIPT_DIR/ml-service/venv/bin/python"

# Auto-install/update dependencies
if [ ! -f "venv/.deps_installed" ] || [ "requirements.txt" -nt "venv/.deps_installed" ]; then
    echo "  Installing Python dependencies (this may take a while on first run)..."
    "$VENV_PYTHON" -m pip install --upgrade pip > /dev/null 2>&1
    "$VENV_PYTHON" -m pip install -r requirements.txt
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
"$SCRIPT_DIR/ml-service/venv/bin/python" src/main.py > /tmp/vi-ml-service.log 2>&1 &
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

# Wait for HTTP endpoints. Allow overrides for slow machines / cold model loads.
BACKEND_READY_TIMEOUT=${BACKEND_READY_TIMEOUT:-30}
ML_READY_TIMEOUT=${ML_READY_TIMEOUT:-180}
FRONTEND_READY_TIMEOUT=${FRONTEND_READY_TIMEOUT:-60}
STRICT_HEALTH_CHECKS=${STRICT_HEALTH_CHECKS:-true}

backend_ready=true
ml_ready=true
frontend_ready=true

wait_for_service "http://localhost:3001/api/jobs/health-check" "Backend" "$BACKEND_READY_TIMEOUT" || backend_ready=false
wait_for_service "http://localhost:8000/health" "ML Service" "$ML_READY_TIMEOUT" || ml_ready=false
wait_for_service "http://localhost:3000" "Frontend" "$FRONTEND_READY_TIMEOUT" || frontend_ready=false

if [ "$STRICT_HEALTH_CHECKS" = "true" ]; then
    if [ "$backend_ready" = false ] || [ "$ml_ready" = false ]; then
        echo ""
        echo "  ✗ Critical service(s) failed health checks. Aborting."
        echo "    Set STRICT_HEALTH_CHECKS=false to keep partial environments running."
        echo "    Backend log:    /tmp/vi-backend.log"
        echo "    ML Service log: /tmp/vi-ml-service.log"
        echo "    Frontend log:   /tmp/vi-frontend.log"
        exit 1
    fi
    if [ "$frontend_ready" = false ]; then
        echo "  ⚠ Frontend did not respond in ${FRONTEND_READY_TIMEOUT}s but backend/ML are up."
        echo "    Tail /tmp/vi-frontend.log if it stays unreachable."
    fi
fi

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
