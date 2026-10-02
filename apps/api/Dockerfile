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
# $PORT overrides the port on platforms that inject one; one worker keeps memory small.
# Proxy headers let per-IP rate limits see the real client behind the tunnel/Vercel proxy.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
