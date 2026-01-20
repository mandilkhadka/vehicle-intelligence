# Production Deployment Guide

This guide covers deploying the Vehicle Intelligence Platform to production.

## Prerequisites

- Docker and Docker Compose installed
- Minimum 8GB RAM and 4 CPU cores recommended
- SSL certificates for HTTPS (recommended)

## Environment Variables

### Backend (.env)

```bash
NODE_ENV=production
PORT=3001
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
ML_SERVICE_URL=http://ml-service:8000
DATABASE_PATH=/app/data/vehicle_intelligence.db
UPLOAD_MAX_SIZE=524288000
RATE_LIMIT_WINDOW_MS=900000
RATE_LIMIT_MAX_REQUESTS=100
LOG_LEVEL=info
```

### ML Service (.env)

```bash
NODE_ENV=production
PORT=8000
CORS_ALLOWED_ORIGINS=https://yourdomain.com
LOG_LEVEL=INFO
```

### Frontend (.env.local)

```bash
NODE_ENV=production
NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api
NEXT_PUBLIC_BACKEND_URL=https://api.yourdomain.com
```

## Docker Deployment

### Development

```bash
docker-compose up --build
```

### Production

```bash
docker-compose -f docker-compose.prod.yml up -d --build
```

## Health Checks

All services expose health check endpoints:

- Backend: `GET /health` and `GET /ready`
- ML Service: `GET /health` and `GET /ready`
- Frontend: `GET /`

## Monitoring

### Logs

View logs for all services:
```bash
docker-compose logs -f
```

View logs for specific service:
```bash
docker-compose logs -f backend
docker-compose logs -f ml-service
docker-compose logs -f frontend
```

### Health Status

Check service health:
```bash
curl http://localhost:3001/health
curl http://localhost:8000/health
curl http://localhost:3000
```

## Scaling

The production docker-compose file includes scaling configuration:

```bash
# Scale backend to 3 instances
docker-compose -f docker-compose.prod.yml up -d --scale backend=3

# Scale ML service to 2 instances
docker-compose -f docker-compose.prod.yml up -d --scale ml-service=2
```

## Security Considerations

1. **HTTPS**: Use a reverse proxy (nginx/traefik) with SSL certificates
2. **CORS**: Update `CORS_ALLOWED_ORIGINS` with your production domains
3. **Rate Limiting**: Adjust rate limits based on your traffic patterns
4. **File Upload Limits**: Set appropriate `UPLOAD_MAX_SIZE` based on your needs
5. **Database**: Consider using PostgreSQL for production instead of SQLite
6. **Secrets**: Use Docker secrets or environment variable management tools

## Backup

### Database Backup

```bash
# Backup SQLite database
docker exec vehicle-intelligence-backend sqlite3 /app/data/vehicle_intelligence.db .dump > backup.sql

# Restore
docker exec -i vehicle-intelligence-backend sqlite3 /app/data/vehicle_intelligence.db < backup.sql
```

### Uploads Backup

```bash
# Backup uploads volume
docker run --rm -v vehicle-intelligence_backend-uploads:/data -v $(pwd):/backup alpine tar czf /backup/uploads-backup.tar.gz /data
```

## Troubleshooting

### Service won't start

1. Check logs: `docker-compose logs [service-name]`
2. Verify environment variables
3. Check port availability
4. Verify Docker resources (memory/CPU)

### ML Service timeout

1. Increase timeout in backend config
2. Check ML service logs for errors
3. Verify GPU availability (if using GPU acceleration)

### Database errors

1. Check database file permissions
2. Verify disk space
3. Check database file integrity

## Performance Tuning

1. **Backend**: Adjust Node.js memory limit if needed
2. **ML Service**: Allocate more CPU/memory for faster processing
3. **Database**: Consider connection pooling for high traffic
4. **Caching**: Add Redis for caching frequently accessed data
