
from fastapi import FastAPI, HTTPException, Request,status
from fastapi.exceptions import RequestValidationError
from backend.__init__ import logger
from backend.common.utils import build_error, json_error 


async def fallback_handler(request: Request, exc: Exception):
    
    body = {
        "detail": "Internal Server Error "
    }

    logger.debug(f"{exc},{type(exc).__name__} fallback handler error occured ")
    
    status_code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
    code = "SERVER_ERROR"
    payload = build_error(code=code, details=body, trace_id=None)
    return json_error(payload, status_code=status_code)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.debug(f"{exc} validation exception error ")
    payload = build_error(code="UNPROCESSABLE_ENTITY", details=exc.errors(), trace_id=None)
    return json_error(payload, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)


async def http_exception_handler(request: Request, exc: HTTPException):
   
    # trace_id = getattr(request.state, "trace_id", None)

    if isinstance(exc.detail, dict) and "code" in exc.detail:
        app_code = exc.detail.get("code")
        app_details = exc.detail.get("details", exc.detail.get("message"))
    else:
        app_code = f"HTTP_{exc.status_code}"
        app_details = exc.detail

    payload = build_error(code=app_code, details=app_details, trace_id=None)
    return json_error(payload, status_code=exc.status_code)


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