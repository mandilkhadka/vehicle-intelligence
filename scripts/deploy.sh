#!/bin/bash

# Production deployment script for Vehicle Intelligence Platform
# Usage: ./scripts/deploy.sh [environment]

set -e

ENVIRONMENT=${1:-production}
COMPOSE_FILE="docker-compose.yml"

if [ "$ENVIRONMENT" = "production" ]; then
    COMPOSE_FILE="docker-compose.prod.yml"
fi

echo "🚀 Deploying Vehicle Intelligence Platform (${ENVIRONMENT})..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ] && [ "$ENVIRONMENT" = "production" ]; then
    echo "⚠️  Warning: .env file not found. Using defaults."
    echo "   Create .env file from .env.example for production deployment."
fi

# Build and start services
echo "📦 Building Docker images..."
docker-compose -f $COMPOSE_FILE build --no-cache

echo "🔄 Starting services..."
docker-compose -f $COMPOSE_FILE up -d

echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check health
echo "🏥 Checking service health..."
BACKEND_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3001/health || echo "000")
ML_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health || echo "000")
FRONTEND_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 || echo "000")

if [ "$BACKEND_HEALTH" = "200" ]; then
    echo "✅ Backend is healthy"
else
    echo "❌ Backend health check failed (HTTP $BACKEND_HEALTH)"
fi

if [ "$ML_HEALTH" = "200" ]; then
    echo "✅ ML Service is healthy"
else
    echo "❌ ML Service health check failed (HTTP $ML_HEALTH)"
fi

if [ "$FRONTEND_HEALTH" = "200" ]; then
    echo "✅ Frontend is healthy"
else
    echo "❌ Frontend health check failed (HTTP $FRONTEND_HEALTH)"
fi

echo ""
echo "📊 Service Status:"
docker-compose -f $COMPOSE_FILE ps

echo ""
echo "✨ Deployment complete!"
echo "   Backend:   http://localhost:3001"
echo "   ML Service: http://localhost:8000"
echo "   Frontend:  http://localhost:3000"
echo ""
echo "View logs: docker-compose -f $COMPOSE_FILE logs -f"
