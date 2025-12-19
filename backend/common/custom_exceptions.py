
from fastapi import FastAPI, HTTPException, Request,status
from fastapi.exceptions import RequestValidationError
from backend.__init__ import logger
from backend.common.utils import build_error, json_error 
from backend.common.constants import request_id_ctx


async def fallback_handler(request: Request, exc: Exception):

    rid = request_id_ctx.get(None)
    body = {"message": "Internal Server Error "}

    logger.error(
        "unexpected.exception",
        extra={
            "path": request.url.path,
            "method": request.method,
            "request_id": rid,
        },
        exc_info=exc,
    )

    status_code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
    code = "SERVER_ERROR"
    
    payload = build_error(code=code, details=body, request_id=rid)
    return json_error(payload, status_code=status_code)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    rid = request_id_ctx.get(None)
    logger.warning(
        "request.validation_failed",
        extra={
            "errors": exc.errors(),
            "path": request.url.path,
            "request_id": rid,
        },
    )
    
    payload = build_error(code="UNPROCESSABLE_ENTITY", details={"message":"invalid request"}, request_id=rid)
    return json_error(payload, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


async def http_exception_handler(request: Request, exc: HTTPException):
   
    rid = request_id_ctx.get(None)

    error_code = f"HTTP_{exc.status_code}"
    status_code = exc.status_code
    message = exc.detail


    payload = build_error(code=error_code, details={"message":message}, request_id=rid)
    return json_error(payload, status_code=status_code)


def register_all_exceptions(app: FastAPI):

    app.add_exception_handler(
        Exception, # catch all unidentified/unhandled exceptions
        fallback_handler
    )

    app.add_exception_handler(
        RequestValidationError, # catch all unidentified/unhandled exceptions
        validation_exception_handler
    )

    app.add_exception_handler(
        HTTPException,
        http_exception_handler
    )