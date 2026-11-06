from contextlib import asynccontextmanager
from starlette.concurrency import run_in_threadpool
from app.core.auth import SESSION_COOKIE, clear_session_cookie, set_session_cookie
from app.core.auth_logging import install_auth_log_filter
from app.repositories.auth import AuthRepository
from app.services.oidc import GoogleOIDC
import ipaddress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import ROOT, Settings
from app.core.test_database import testing_enabled
from app.db.migrate import migrate
from app.db.seed import seed
from app.repositories.missions import MissionRepository
from app.routers import api, web, planning, diary, auth, receipts
from app.repositories.receipts import ReceiptRepository
from app.services.receipt_storage import TemporaryReceiptStorage
from app.services.local_receipt_storage import LocalReceiptStorage
from app.repositories.itinerary import ItineraryRepository
from app.repositories.diary import DiaryRepository


def create_app(settings: Settings | None = None):
    configuration = settings or Settings.from_env()
    install_auth_log_filter()

    @asynccontextmanager
    async def lifespan(application):
        configuration.validate()
        migrate(configuration.database_path)
        seed(configuration.database_path)
        application.state.repository = MissionRepository(configuration.database_path)
        application.state.itinerary = ItineraryRepository(configuration.database_path)
        application.state.diary = DiaryRepository(configuration.database_path)
        for mission in application.state.repository.list():
            application.state.itinerary.import_legacy(mission)
        if not configuration.dev_no_auth and configuration.auth_ready:
            application.state.auth.provision()
        storage = None
        if configuration.receipts_synthetic_enabled:
            if configuration.receipts_storage_backend=="local":
                storage = LocalReceiptStorage(configuration.database_path,configuration.receipts_private_dir)
                try:
                    storage.reconcile()
                except Exception:
                    storage.close()
                    raise
            else:
                storage = TemporaryReceiptStorage(configuration.database_path)
            application.state.receipt_storage = storage
            application.state.receipts = ReceiptRepository(configuration.database_path, storage)
        try:
            yield
        finally:
            if storage:
                storage.close()

    application = FastAPI(title="SECCO Global PE", lifespan=lifespan,
                          docs_url=None, redoc_url=None, openapi_url=None)
    application.state.settings = configuration
    application.state.auth = AuthRepository(configuration)
    application.state.oidc = GoogleOIDC(configuration)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost","127.0.0.1","[::1]","testserver"])

    @application.middleware("http")
    async def local_only_and_headers(request: Request, call_next):
        qa_instance=request.headers.get("x-secco-qa-instance")
        if qa_instance and (not testing_enabled() or qa_instance!=getattr(application.state,"qa_instance",None)):
            return JSONResponse({"detail":"Cliente de QA recusado neste servidor."},status_code=403)
        host = request.client.host if request.client else ""
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = host == "testclient"
        if not local:
            return JSONResponse({"detail": "Acesso disponível somente neste computador."}, status_code=403)
        request.state.user = None
        request.state.auth_csrf = None
        request.state.session_replaced = False
        session = None
        path = request.url.path
        public = path in ("/login","/auth/google","/auth/google/callback","/auth/logout","/health") or path.startswith("/static/")
        if testing_enabled() and getattr(application.state,"qa_instance",None) and path in ("/__qa__/identity","/__qa__/shutdown","/__qa__/authorize"):
            public = True
        if not configuration.dev_no_auth:
            if configuration.auth_ready and not path.startswith("/static/") and path!="/health":
                session = await run_in_threadpool(application.state.auth.resolve_session, request.cookies.get(SESSION_COOKIE))
                if session:
                    request.state.user = session["user"]
                    request.state.auth_csrf = session["csrf"]
            if not public and not request.state.user:
                is_json = path.startswith("/api/") or request.method not in ("GET","HEAD") or "application/json" in request.headers.get("accept","")
                if is_json:
                    response = JSONResponse({"detail":"Autenticação necessária." if configuration.auth_ready else "A configuração do acesso está pendente."},
                        status_code=401 if configuration.auth_ready else 503)
                else:
                    response = RedirectResponse("/login"+("?erro=sessao-expirada" if request.cookies.get(SESSION_COOKIE) else ""),status_code=303)
            else:
                response = await call_next(request)
            if not request.state.session_replaced:
                if session and session["new_token"]:
                    set_session_cookie(response,configuration,session["new_token"],session["expires_at"],application.state.auth.clock())
                elif not session and request.cookies.get(SESSION_COOKIE) and not path.startswith("/static/") and path!="/health":
                    clear_session_cookie(response,configuration)
        else:
            response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data: blob:; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self' https://accounts.google.com; worker-src 'self'; manifest-src 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer" if path=="/auth/google/callback" else "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if not request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(404)
    async def not_found(request, exception):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Missão não encontrada"}, status_code=404)
        response = web.render(request,"error.html",title="Página não encontrada")
        response.status_code = 404
        return response

    @application.exception_handler(403)
    async def forbidden(request, exception):
        if request.url.path.startswith("/api/") or "application/json" in request.headers.get("accept",""):
            return JSONResponse({"detail":exception.detail},status_code=403)
        response = web.render(request,"access_denied.html",title="Acesso não permitido",message=exception.detail)
        response.status_code = 403
        return response

    application.include_router(auth.router)
    application.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")
    application.include_router(receipts.router)
    application.include_router(diary.router)
    application.include_router(planning.router)
    application.include_router(web.router)
    application.include_router(api.router)

    @application.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok", "ambiente": configuration.app_env}

    return application


app = create_app()
