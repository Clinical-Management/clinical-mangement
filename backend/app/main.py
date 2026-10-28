import asyncio
import hmac
import logging
from contextlib import asynccontextmanager

import jwt

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import DomainError
from app.core.security import decode_access_token
from app.history.engine import EngineError
from app.db.mongodb import close_mongo_connection, connect_to_mongo, mongo
from app.services import audit_service, notify_service

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await connect_to_mongo()
    worker = asyncio.create_task(notify_service.run_worker(lambda: mongo.db)) if settings.notifications_worker else None
    yield
    if worker:
        worker.cancel()
    await close_mongo_connection()


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def audit_requests(request: Request, call_next):
    """Logs signed-in users' views and changes of patient records (see audit_service)."""
    response = await call_next(request)
    auth = request.headers.get("authorization", "")
    path = request.url.path
    if auth.lower().startswith("bearer ") and path.startswith(settings.api_prefix) and response.status_code != 401:
        try:
            claims = decode_access_token(auth[7:])
        except jwt.PyJWTError:
            return response
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client and request.client.host)
        try:
            await audit_service.log_request(
                mongo.db, path=path[len(settings.api_prefix) :], method=request.method, status=response.status_code, claims=claims, ip=ip
            )
        except Exception:  # never fail the user's request because of logging
            log.exception("audit log write failed")
    return response


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(EngineError)
async def engine_error_handler(_: Request, exc: EngineError):
    # The UI offers typed chat / manual entry by staff when the assistant is unavailable
    return JSONResponse(status_code=503, content={"detail": {"code": "ai_unavailable", "message": str(exc)}})


app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/cron/notifications", include_in_schema=False)
async def cron_notifications(request: Request):
    """One worker tick for hosts without a long-running process (Vercel Cron sends the bearer secret)."""
    from app.services import reminder_service

    if not settings.cron_secret or not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {settings.cron_secret}"):
        return JSONResponse(status_code=401, content={"detail": "unauthorized"})
    await reminder_service.queue_due(mongo.db)
    return {"sent": await notify_service.dispatch_due(mongo.db)}


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
