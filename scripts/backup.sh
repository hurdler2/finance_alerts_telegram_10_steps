#!/bin/sh
# PostgreSQL daily backup script.
# Runs inside the `backup` container; called by cron.
# Keeps last 7 backups, deletes older ones.

set -e

BACKUP_DIR="/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="${BACKUP_DIR}/finance_alerts_${TIMESTAMP}.sql.gz"

echo "[backup] Starting pg_dump at ${TIMESTAMP}"

pg_dump \
  -h postgres \
  -U "${POSTGRES_USER:-finance_user}" \
  "${POSTGRES_DB:-finance_alerts}" \
  | gzip > "${FILENAME}"

echo "[backup] Saved: ${FILENAME}"

# Remove backups older than 7 days
find "${BACKUP_DIR}" -name "finance_alerts_*.sql.gz" -mtime +7 -delete
echo "[backup] Cleaned old backups (>7 days)"
