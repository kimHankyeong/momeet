from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """업무 오류. 응답은 항상 {"error": {"code", "message"}} 형태."""

    def __init__(self, code: str, message: str, status_code: int = 400, extra: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}


def _body(code: str, message: str, extra: dict | None = None) -> dict:
    err = {"code": code, "message": message}
    if extra:
        err.update(extra)
    return {"error": err}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        headers = {}
        if "retry_after" in exc.extra:
            headers["Retry-After"] = str(exc.extra["retry_after"])
        return JSONResponse(_body(exc.code, exc.message, exc.extra), status_code=exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        # 기본 핸들러는 입력값(input)을 그대로 돌려주므로 PIN/비밀번호가 응답에 섞일 수 있다. 필드 위치와 사유만 낸다.
        fields = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "reason": e["type"]}
            for e in exc.errors()
        ]
        return JSONResponse(_body("VALIDATION_ERROR", "입력값이 올바르지 않습니다.", {"fields": fields}), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        # 내부 오류 상세/스택은 응답에 싣지 않는다
        return JSONResponse(_body("INTERNAL_ERROR", "서버 오류가 발생했습니다."), status_code=500)
