#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must be set to the backup source database}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output="$BACKUP_DIR/healthcare-${timestamp}.dump"

# pg_dump custom format supports point-in-time restore workflows. Encrypt the
# resulting object with the deployment's KMS/object-storage layer before upload.
pg_dump --dbname="$DATABASE_URL" --format=custom --no-owner --no-privileges --file="$output"
pg_restore --list "$output" >/dev/null
sha256sum "$output" > "$output.sha256"
printf 'Created and verified %s\n' "$output"
