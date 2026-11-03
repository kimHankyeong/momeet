from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.errors import install_error_handlers
from app.routers import conditions, meetings, proposals


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # 개발용. 운영 스키마 변경은 마이그레이션 도구(Alembic)로 관리한다.
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="모밋 백엔드 A (약속방·인증·진행 상태)", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        # 인증은 Authorization 헤더 토큰 방식이라 쿠키를 허용하지 않는다 (CSRF 표면 없음)
        allow_credentials=False,
    )
    install_error_handlers(app)

    app.include_router(meetings.router)
    app.include_router(proposals.router)
    app.include_router(conditions.router)

    @app.get("/health", tags=["system"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
