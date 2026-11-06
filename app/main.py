from contextlib import asynccontextmanager
import ipaddress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import ROOT, Settings
from app.db.migrate import migrate
from app.db.seed import seed
from app.repositories.missions import MissionRepository
from app.routers import api, web, planning
from app.repositories.itinerary import ItineraryRepository


def create_app(settings: Settings | None = None):
    configuration = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application):
        configuration.validate()
        migrate(configuration.database_path)
        seed(configuration.database_path)
        application.state.repository = MissionRepository(configuration.database_path)
        application.state.itinerary = ItineraryRepository(configuration.database_path)
        for mission in application.state.repository.list():
            application.state.itinerary.import_legacy(mission)
        yield

    application = FastAPI(title="SECCO Global PE", lifespan=lifespan,
                          docs_url=None, redoc_url=None, openapi_url=None)
    application.state.settings = configuration
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost","127.0.0.1","[::1]","testserver"])

    @application.middleware("http")
    async def local_only_and_headers(request: Request, call_next):
        host = request.client.host if request.client else ""
        try:
            local = ipaddress.ip_address(host).is_loopback
        except ValueError:
            local = host == "testclient"
        if not local:
            return JSONResponse({"detail": "Acesso disponível somente neste computador."}, status_code=403)
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'; worker-src 'self'; manifest-src 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
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

    application.mount("/static", StaticFiles(directory=ROOT / "app" / "static"), name="static")
    application.include_router(planning.router)
    application.include_router(web.router)
    application.include_router(api.router)

    @application.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok", "ambiente": configuration.app_env}

    return application


app = create_app()
