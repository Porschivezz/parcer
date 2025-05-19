import uvicorn

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager

from core.logger import LOGGING   # noqa
from core.config import settings

from db.init_db import init_db
from api.v1.api_router import api_router


def init_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db()
        yield
        pass

    app = FastAPI(
        title=settings.PROJECT_NAME,
        docs_url=f'{settings.API_VERSION_PREFIX}/docs',
        redoc_url=f'{settings.API_VERSION_PREFIX}/redoc',
        openapi_url=f'{settings.API_VERSION_PREFIX}/openapi.json',
        default_response_class=ORJSONResponse,
        lifespan=lifespan
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.API_VERSION_PREFIX)

    app.secret_key = settings.SECRET_KEY

    return app


app = init_app()


if __name__ == '__main__':
    uvicorn.run(
        'main:app',
        host=settings.PROJECT_HOST, port=settings.PROJECT_PORT,
        workers=settings.ASGI_WORKERS, log_config=LOGGING,
        access_log=True, reload=False
    )
