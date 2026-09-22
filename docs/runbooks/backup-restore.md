# Backup and restore runbook

The production database backup policy is encrypted, access-controlled, and
tested by restoring into an isolated database. Backups must never be restored
over production as a verification step.

## Create a backup

```bash
DATABASE_URL='postgresql://...' BACKUP_DIR='./backups' ./infra/backup/backup.sh
```

Upload the dump and checksum to the approved encrypted object-storage location
using the deployment KMS key. Do not place database credentials in a command
history, CI log, or backup filename.

## Verify a restore

Provision a disposable PostgreSQL database, apply the dump, then run:

```bash
BACKUP_FILE='./backups/healthcare-<timestamp>.dump' \
RESTORE_DATABASE_URL='postgresql://...' \
ISOLATED_RESTORE=YES \
CONFIRM_RESTORE=YES ./infra/backup/restore-verify.sh
```

`ISOLATED_RESTORE=YES` is an operator assertion that the target is a
disposable, isolated database. If `DATABASE_URL` is also present, the script
rejects an identical source and target URL.

Record the restore timestamp, dump checksum, schema migration version, forced
RLS count, and operator in the release evidence. Destroy the disposable restore
database and any local dump after verification according to the retention policy.
