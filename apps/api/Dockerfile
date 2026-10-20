# syntax=docker/dockerfile:1
# Production image for the FastAPI backend (any container host; see docker-compose.yml).
# Build context: apps/api. Dependencies ship wheels, so no compiler is needed.
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .
RUN chmod +x scripts/docker-entrypoint.sh \
    && useradd --system --create-home appuser \
    && mkdir -p /tmp/healthcare-private /tmp/healthcare-public \
    && chown -R appuser /app /tmp/healthcare-private /tmp/healthcare-public
USER appuser
EXPOSE 8000
ENTRYPOINT ["scripts/docker-entrypoint.sh"]
# $PORT overrides the port on platforms that inject one; WEB_CONCURRENCY controls worker count.
# Proxy headers let per-IP rate limits see the real client behind the tunnel/Vercel proxy,
# but we only trust forwarded headers from FORWARDED_ALLOW_IPS (the proxy's IP/CIDR) so a
# direct client cannot spoof its address. Defaults to loopback; override per deployment.
CMD ["sh", "-c", "exec gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-4} --keep-alive 65 --graceful-timeout 30 --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
