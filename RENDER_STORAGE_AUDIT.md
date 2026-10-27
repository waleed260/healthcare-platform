# Storage Audit

## Storage Architecture

**Source**: `apps/api/app/modules/files/storage.py`

Dual-backend adapter controlled by `STORAGE_BACKEND` env var:
- `local` — writes to filesystem paths (`/tmp/healthcare-private`, `/tmp/healthcare-public`)
- `supabase` — writes to Supabase Storage buckets via REST API

### Local Backend

| Operation | Implementation | Notes |
|-----------|---------------|-------|
| `put_private_object` | Atomic write via temp file + `os.replace` | Permissions: 0o600 |
| `read_private_object` | `Path.read_bytes()` | |
| `delete_private_object` | `Path.unlink(missing_ok=True)` | |
| `put_public_object` | Atomic write via temp file + `os.replace` | Permissions: 0o644 |
| `read_public_object` | `Path.read_bytes()` | |

**Path traversal protection**: `_safe_path()` and `_safe_public_path()` reject absolute paths, `..` components, and paths that resolve outside the root. **Verified safe.**

### Supabase Backend

| Operation | Implementation | Notes |
|-----------|---------------|-------|
| `put_private_object` | `POST` to Supabase Storage API | `x-upsert: false` |
| `read_private_object` | `GET` from Supabase Storage API | |
| `delete_private_object` | `DELETE` from Supabase Storage API | |
| `put_public_object` | `POST` to public bucket | |
| `read_public_object` | `GET` from public URL path | |

Uses `Authorization: Bearer <service_role_key>` and `apikey` headers. 30s timeout.

### Readiness Check

`check_storage_readiness()`:
- **Local**: Verifies directories exist and are readable/writable/executable. Creates them if missing.
- **Supabase**: Issues `GET /storage/v1/bucket/{bucket}` for both buckets. 2s timeout.

## Render Free Tier Implications

**Render free tier filesystem is ephemeral.** Files written to `/tmp/healthcare-*` survive:
- During the current container lifecycle
- Across requests within the same container

Files are **lost** on:
- Deploy/redeploy
- Service restart
- Spin-down (15 min idle) followed by wake

### Impact on Each Feature

| Feature | Storage Used | Impact of File Loss |
|---------|-------------|-------------------|
| Patient documents | `put_private_object` | Document content lost; DB row references a missing file |
| Patient media (images) | `put_private_object` | Media lost; scan_status row points to nothing |
| Website images | `put_public_object` | Website images disappear |
| Data exports | `put_private_object` | Export JSON lost before download window |
| Document scanning | `read_private_object` | Scan reads the file; if file is lost before scan, job fails and retries |

### Scanning and Encryption Policies

Scanning happens via background jobs that read the file from storage and validate content. If `STORAGE_BACKEND=local` and the file is lost before the scan job runs:
1. `read_private_object` raises `FileNotFoundError`
2. The job handler catches the exception
3. `fail_job()` is called with bounded retries
4. After 5 failures, job is marked permanently failed
5. `scan_status` remains `pending` — the file is never marked `clean`

**This means files uploaded during one container lifecycle that survive scanning are correctly validated. Files lost before scanning are correctly flagged as failed. No false `clean` status.**

## Recommendation

| Scenario | Backend | Acceptable? |
|----------|---------|-------------|
| Staging with no real patient data | `local` | YES — files may be lost but no PHI at risk |
| Staging with test uploads | `local` | YES — understand files are transient |
| Any real patient data | `supabase` | REQUIRED |

### Supabase Configuration Needed

If switching to `STORAGE_BACKEND=supabase`, these env vars must be set:

| Variable | Required |
|----------|----------|
| `SUPABASE_URL` | Yes — `https://xxx.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes — secret key with storage access |
| `SUPABASE_PRIVATE_BUCKET` | No — defaults to `private-healthcare` |
| `SUPABASE_PUBLIC_BUCKET` | No — defaults to `public-healthcare` |

Buckets must be pre-created in the Supabase dashboard. The private bucket must have RLS enabled. The public bucket must allow anonymous reads.

## Verified Facts

| Check | Result |
|-------|--------|
| Path traversal protection | SAFE — `_safe_path` rejects `..` and absolute paths |
| Atomic writes | YES — temp file + `os.replace` |
| Private file permissions | 0o600 — owner-only |
| Public file permissions | 0o644 — world-readable |
| Supabase adapter exists and is functional | YES — full CRUD implemented |
| Health check covers storage | YES — `check_storage_readiness()` in `/health/ready` |
| File loss causes false clean status | NO — scan fails, file stays `pending` |
