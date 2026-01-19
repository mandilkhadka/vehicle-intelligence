#!/bin/bash

# Start script for Vehicle Intelligence Platform
# This script starts all three services

echo "Starting Vehicle Intelligence Platform services..."

# Function to cleanup on exit
cleanup() {
    echo "Stopping all services..."
    kill $BACKEND_PID $ML_PID $FRONTEND_PID 2>/dev/null
    exit
}

trap cleanup SIGINT SIGTERM

# Start Backend
echo "Starting Backend API (port 3001)..."
cd backend
npm run dev &
BACKEND_PID=$!
cd ..

# Wait a bit for backend to start
sleep 3

# Start ML Service
echo "Starting ML Service (port 8000)..."
cd ml-service
source venv/bin/activate
python3 src/main.py &
ML_PID=$!
cd ..

# Wait a bit for ML service to start
sleep 3

# Start Frontend
echo "Starting Frontend (port 3000)..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "All services started!"
echo "Backend: http://localhost:3001"
echo "ML Service: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for all processes
wait
