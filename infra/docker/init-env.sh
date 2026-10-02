#!/usr/bin/env bash
# Create docker.env (git-ignored, mode 600) with freshly generated secrets. Refuses to overwrite.
#   infra/docker/init-env.sh [https://your-frontend.example]
# Back up docker.env: FIELD_ENCRYPTION_KEYS decrypts stored data; losing it makes encrypted fields unreadable.
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -e docker.env ] && { echo "docker.env already exists; not overwriting (back it up, then delete it to regenerate)"; exit 1; }
FRONTEND="${1:-https://web-eight-flax-pmiw08soee.vercel.app}"
HOST="${FRONTEND#https://}"; HOST="${HOST%%/*}"
rand() { head -c 36 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n'; }
fernet() { head -c 32 /dev/urandom | base64 | tr '+/' '-_'; }   # 32 random bytes, urlsafe base64 = valid Fernet key
umask 077
cat > docker.env <<ENV
APP_ENV=staging
POSTGRES_OWNER_PASSWORD=$(rand)
HEALTHCARE_RUNTIME_PASSWORD=$(rand)
SESSION_HMAC_KEY=$(rand)$(rand)
FIELD_ENCRYPTION_KEYS=$(fernet)
COOKIE_DOMAIN=${HOST}
CSRF_ALLOWED_ORIGINS=${FRONTEND}
CORS_ORIGINS=${FRONTEND}
PUBLIC_APP_URL=${FRONTEND}
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=
ENV
echo "created docker.env (mode 600). Fake data only while APP_ENV=staging. Back up FIELD_ENCRYPTION_KEYS."
