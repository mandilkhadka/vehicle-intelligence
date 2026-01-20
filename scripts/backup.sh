#!/bin/bash

# Backup script for Vehicle Intelligence Platform
# Usage: ./scripts/backup.sh [backup-dir]

set -e

BACKUP_DIR=${1:-./backups}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"

mkdir -p "$BACKUP_PATH"

echo "📦 Creating backup at $BACKUP_PATH..."

# Backup database
echo "💾 Backing up database..."
docker exec vehicle-intelligence-backend sqlite3 /app/data/vehicle_intelligence.db .dump > "$BACKUP_PATH/database.sql" 2>/dev/null || {
    echo "⚠️  Database backup failed (database might not exist yet)"
}

# Backup uploads
echo "📁 Backing up uploads..."
docker run --rm \
    -v vehicle-intelligence_backend-uploads:/data:ro \
    -v "$(pwd)/$BACKUP_PATH":/backup \
    alpine tar czf /backup/uploads.tar.gz -C /data . 2>/dev/null || {
    echo "⚠️  Uploads backup failed (uploads volume might not exist)"
}

# Create backup info file
cat > "$BACKUP_PATH/backup-info.txt" << EOF
Backup created: $(date)
Services:
- Backend: $(docker inspect vehicle-intelligence-backend --format='{{.State.Status}}' 2>/dev/null || echo "not running")
- ML Service: $(docker inspect vehicle-intelligence-ml-service --format='{{.State.Status}}' 2>/dev/null || echo "not running")
- Frontend: $(docker inspect vehicle-intelligence-frontend --format='{{.State.Status}}' 2>/dev/null || echo "not running")
EOF

echo "✅ Backup completed: $BACKUP_PATH"
echo "   Files:"
ls -lh "$BACKUP_PATH"
