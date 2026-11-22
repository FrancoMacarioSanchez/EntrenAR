#!/usr/bin/env bash
# Backup de EntrenAR: dump completo (todos los gimnasios = todos los schemas) + fotos/archivos.
# Retención: 14 diarios. Copiá /srv/backups/entrenar fuera del VPS (rclone, Hostinger backups, etc.).
set -euo pipefail
set -a; source /srv/entrenar/backend/.env; set +a
DEST=${BACKUP_DIR:-/srv/backups/entrenar}
STAMP=$(date +%Y%m%d-%H%M)
mkdir -p "$DEST"
PGPASSWORD="$DB_PASSWORD" pg_dump -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" -U "$DB_USER" -Fc "$DB_NAME" \
  > "$DEST/db-$STAMP.dump"
tar -czf "$DEST/media-$STAMP.tar.gz" -C /srv/entrenar/backend media 2>/dev/null || true
find "$DEST" -type f -mtime +14 -delete
echo "$(date -Is) backup OK: $DEST/db-$STAMP.dump"
# Restaurar: pg_restore -h localhost -U entrenar -d entrenar --clean --if-exists db-AAAAMMDD-HHMM.dump
