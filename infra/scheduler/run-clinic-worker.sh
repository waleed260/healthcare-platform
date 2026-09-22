#!/usr/bin/env bash
set -euo pipefail

# Trusted schedulers must supply the tenant explicitly. This entrypoint never
# discovers clinics and never accepts database credentials as arguments.
clinic_id="${1:?usage: run-clinic-worker.sh CLINIC_UUID JOB_TYPE}"
job_type="${2:?usage: run-clinic-worker.sh CLINIC_UUID JOB_TYPE}"

if [[ ! "$clinic_id" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
  echo "clinic ID must be a UUID" >&2
  exit 2
fi

case "$job_type" in
  document_scan|document_metadata_encrypt|website_media_scan|export|retention_cleanup|follow_up_overdue_notification) ;;
  *)
    echo "unsupported job type: $job_type" >&2
    exit 2
    ;;
esac

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root/apps/api"
exec env PYTHONPATH=. python -m app.worker --clinic-id "$clinic_id" --job-type "$job_type" --once
