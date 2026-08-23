#!/bin/bash
# Backup giornaliero del database Argo. Tiene gli ultimi 14 giorni.
set -e
DIR=/root/argo/backup/dumps
mkdir -p "$DIR"
FILE="$DIR/argo_$(date +%Y%m%d_%H%M).sql.gz"
docker exec argo-db-1 pg_dump -U argo argo | gzip > "$FILE"
find "$DIR" -name 'argo_*.sql.gz' -mtime +14 -delete
echo "$(date '+%F %T') backup ok: $(du -h "$FILE" | cut -f1)"
