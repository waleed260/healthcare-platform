from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
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
from app.db.session import engine
from sqlalchemy import text
from time import monotonic
from app.core.observability import request_metrics

settings = get_settings()
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID", "Idempotency-Key", "X-Clinic-Slug", "X-Management-Token", "X-Export-Access-Token"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    started = monotonic()
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
    request_metrics.observe(request.method, route, response.status_code, (monotonic() - started) * 1000)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
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
    except Exception:
        from fastapi import HTTPException

        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"status": "not_ready"})
    return {"status": "ready"}


@app.get("/ready", tags=["system"], include_in_schema=False)
def ready_legacy() -> dict[str, str]:
    return health_ready()
