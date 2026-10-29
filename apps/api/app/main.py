from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from uuid import uuid4

from app.api.v1.routes import router as v1_router
from app.core.config import get_settings
from app.modules.identity.routes import router as identity_router
from app.modules.authorization.routes import router as authorization_router
from app.modules.catalog.routes import router as catalog_router, catalog_router as catalog_setup_router
from app.modules.staff.routes import router as staff_router
from app.modules.websites.routes import router as websites_router, public_router as public_websites_router
from app.modules.appointments.routes import router as appointments_router, availability_router, catalog_router as public_catalog_router, appointment_router, management_router, question_router
from app.modules.operations.routes import router as operations_router
from app.modules.crm.routes import router as crm_router, tags_router as crm_tags_router
from app.modules.files.routes import router as files_router
from app.modules.governance.routes import router as governance_router
from app.modules.governance.admin_routes import router as platform_admin_router
from app.modules.scheduling.routes import router as scheduling_router
from app.modules.blueprint_core.routes import billing_router, lead_router, specialty_router
from app.modules.clinical.routes import prescription_router, router as clinical_router
from app.modules.packages.routes import router as packages_router
from app.modules.inventory.routes import router as inventory_router
from app.modules.inventory.supplier_routes import router as supplier_router
from app.modules.inventory.warehouse_routes import router as warehouse_router
from app.modules.inventory.purchase_routes import router as purchase_router
from app.modules.inventory.transfer_routes import router as transfer_router
from app.modules.identity.security_routes import router as account_security_router
from app.modules.identity.google import router as google_auth_router
from app.modules.clinical_tools.routes import router as clinical_tools_router
from app.modules.clinical_media.public_routes import public_router as patient_media_public_router
from app.modules.website_content.routes import public_router as website_content_public_router, router as website_content_router
from app.modules.websites.seo_routes import router as website_seo_router
from app.modules.website_library.routes import router as website_library_router
from app.modules.finance.routes import receipt_router, router as finance_router
from app.modules.upgrades.routes import admin_router as upgrade_admin_router, router as upgrade_router
from app.modules.clinical_media.routes import router as clinical_media_router
from app.modules.clinical_forms.routes import patient_router as clinical_form_patient_router, router as clinical_forms_router
from app.modules.tasks.routes import router as tasks_router
from app.modules.encounters.routes import router as encounters_router
from app.modules.files.storage import check_storage_readiness
from app.db.session import engine
from sqlalchemy import text
from time import monotonic
from app.core.observability import configure_logging, initialize_sentry, request_metrics

settings = get_settings()
configure_logging()
initialize_sentry(settings)
app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
    description="Versioned modular monolith API for the Healthcare Platform.",
)
app.include_router(v1_router)
app.include_router(identity_router)
app.include_router(authorization_router)
app.include_router(catalog_router)
app.include_router(catalog_setup_router)
app.include_router(staff_router)
app.include_router(websites_router)
app.include_router(public_websites_router)
app.include_router(appointments_router)
app.include_router(availability_router)
app.include_router(public_catalog_router)
app.include_router(appointment_router)
app.include_router(management_router)
app.include_router(question_router)
app.include_router(operations_router)
app.include_router(crm_router)
app.include_router(crm_tags_router)
app.include_router(files_router)
app.include_router(governance_router)
app.include_router(platform_admin_router)
app.include_router(scheduling_router)
app.include_router(specialty_router)
app.include_router(lead_router)
app.include_router(billing_router)
app.include_router(clinical_router)
app.include_router(prescription_router)
app.include_router(packages_router)
app.include_router(inventory_router)
app.include_router(supplier_router)
app.include_router(warehouse_router)
app.include_router(purchase_router)
app.include_router(transfer_router)
app.include_router(receipt_router)
app.include_router(finance_router)
app.include_router(upgrade_router)
app.include_router(website_library_router)
app.include_router(website_seo_router)
app.include_router(google_auth_router)
app.include_router(account_security_router)
app.include_router(website_content_router)
app.include_router(website_content_public_router)
app.include_router(patient_media_public_router)
app.include_router(clinical_tools_router)
app.include_router(upgrade_admin_router)
app.include_router(clinical_media_router)
app.include_router(clinical_forms_router)
app.include_router(clinical_form_patient_router)
app.include_router(tasks_router)
app.include_router(encounters_router)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in settings.cors_allowed_origins if "*" not in o],
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID", "Idempotency-Key", "X-Clinic-Slug", "X-Management-Token", "X-Export-Access-Token", "X-Document-Access-Token", "X-Document-Expires", "X-Original-Filename", "X-Alt-Text", "X-Preview-Token"],
)


_CACHEABLE_REF_PATHS = frozenset({
    "/api/v1/branches", "/api/v1/doctors", "/api/v1/services",
    "/api/v1/holidays", "/api/v1/catalog/service-templates",
})


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    started = monotonic()
    path = request.url.path
    if path.startswith("/api/v1/") and not path.startswith("/api/v1/public/") and not path.startswith("/api/v1/auth/login"):
        cookie_val = request.cookies.get(settings.session_cookie_name)
        if cookie_val:
            from app.core.rate_limit import check_rate_limit
            is_write = request.method not in ("GET", "HEAD", "OPTIONS")
            retry_after = check_rate_limit(cookie_val, "global", is_write)
            if retry_after is not None:
                return JSONResponse(
                    status_code=429,
                    content={"error": {"code": "RATE_LIMITED", "message": "Too many requests. Please slow down."}},
                    headers={"Retry-After": str(retry_after)},
                )
    incoming_id = request.headers.get("X-Request-ID", "")
    try:
        from uuid import UUID

        UUID(incoming_id)
        request_id = incoming_id
    except (ValueError, AttributeError):
        request_id = str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    route = getattr(request.scope.get("route"), "path", "unmatched")
    elapsed_ms = (monotonic() - started) * 1000
    request_metrics.observe(request.method, route, response.status_code, elapsed_ms)
    import logging
    logging.getLogger("healthcare.request").info(
        "request.complete",
        extra={
            "request_id": request_id,
            "method": request.method,
            "route": route,
            "status_code": response.status_code,
            "elapsed_ms": round(elapsed_ms, 2),
        },
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data: blob: https:; connect-src 'self'; font-src 'self' https://fonts.gstatic.com; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    path = request.url.path
    if request.method == "GET" and response.status_code == 200 and "Cache-Control" not in response.headers:
        if path.startswith("/api/v1/public/"):
            response.headers["Cache-Control"] = "public, max-age=120, s-maxage=300, stale-while-revalidate=600"
            response.headers["Vary"] = "Accept-Encoding"
            response.headers["CDN-Cache-Control"] = "public, max-age=300"
        elif path == "/health/live" or path == "/health" or path == "/health/ready":
            response.headers["Cache-Control"] = "no-cache"
        elif path in _CACHEABLE_REF_PATHS:
            response.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=120"
        elif path == "/api/v1/auth/me" or path == "/api/v1/clinic/context":
            response.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=60"
        elif path.startswith("/api/"):
            response.headers["Cache-Control"] = "private, no-cache, max-age=0"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    fields = {".".join(str(part) for part in error["loc"]): error["msg"] for error in exc.errors()}
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": {"code": "INVALID_INPUT", "message": "The request could not be validated.", "fields": fields}, "meta": {"request_id": getattr(request.state, "request_id", str(uuid4()))}})


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        error = exc.detail["error"]
    else:
        error = {"code": "HTTP_ERROR", "message": str(exc.detail), "fields": None}
    return JSONResponse(status_code=exc.status_code, content={"error": error, "meta": {"request_id": getattr(request.state, "request_id", str(uuid4()))}})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    import logging
    request_id = getattr(request.state, "request_id", str(uuid4()))
    logging.getLogger("healthcare.error").exception("unhandled_exception request_id=%s exc_type=%s", request_id, type(exc).__name__)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred. Please try again.", "fields": None}, "meta": {"request_id": request_id}})




@app.on_event("startup")
def _warm_pool():
    """Pre-create pool_size connections so first burst avoids cold-start."""
    import logging
    import time
    pool_size = settings.db_pool_size
    for attempt in range(3):
        conns = []
        try:
            for _ in range(pool_size):
                conns.append(engine.connect())
            for c in conns:
                c.execute(text("SELECT 1"))
            logging.getLogger("healthcare.startup").info("connection_pool_warmed count=%d", pool_size)
            return
        except Exception:
            logging.getLogger("healthcare.startup").warning("pool_warmup_attempt_%d_failed", attempt + 1)
            if attempt < 2:
                time.sleep(1 * (attempt + 1))
        finally:
            for c in conns:
                try:
                    c.close()
                except Exception:
                    pass
    logging.getLogger("healthcare.startup").error("pool_warmup_exhausted_retries")


@app.on_event("startup")
def _start_embedded_worker():
    """Run the scan worker in-process when there's no separate worker service."""
    import os
    if os.environ.get("RUN_WORKER_IN_PROCESS", "").lower() not in ("true", "1"):
        return
    import logging
    import threading
    from scripts.scan_worker import main as worker_main
    t = threading.Thread(target=worker_main, daemon=True, name="embedded-scan-worker")
    t.start()
    logging.getLogger("healthcare.startup").info("embedded_scan_worker_started")


@app.get("/health/live", tags=["system"])
def health_live() -> dict[str, str]:
    """Liveness probe: prove only that the API process is serving requests."""
    return {"status": "ok"}


@app.get("/health", tags=["system"], include_in_schema=False)
def health_legacy() -> dict[str, str]:
    """Compatibility alias for existing probes; keep the response non-sensitive."""
    return health_live()


@app.get("/health/ready", tags=["system"])
def health_ready() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        storage_ready = check_storage_readiness()
    except Exception:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"status": "not_ready"})
    if not storage_ready:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"status": "not_ready"})
    return {"status": "ready"}


@app.get("/ready", tags=["system"], include_in_schema=False)
def ready_legacy() -> dict[str, str]:
    return health_ready()
