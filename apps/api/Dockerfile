# syntax=docker/dockerfile:1
# Production image for the FastAPI backend (Render/any container host).
# Build context: apps/api. Dependencies ship wheels, so no compiler is needed.
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
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
# Render injects $PORT. One worker keeps memory inside the 512 MB free tier.
# Proxy headers let per-IP rate limits see the real client behind Render/Vercel.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
