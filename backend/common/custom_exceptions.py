from collections.abc import Callable
from typing import Any, Type, Union
from fastapi import FastAPI, HTTPException, Request,status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from backend.__init__ import logger
from backend.common.utils import build_error 

class PhyllException(Exception):
    """
    Base for all domain errors
      - subclasses *must* define `status_code` and `detail`
    """
    detail: str
    status_code: int

    def __init__(
        self,*,detail: str | None = None,status_code: int | None = None,**kwargs: Any,):

        # ensure subclass defined defaults
        if status_code is None and getattr(self.__class__, "status_code", None) is None:
            raise TypeError("Subclass of PhyllException must define `status_code`")
        if detail is None and getattr(self.__class__, "detail", None) is None:
            raise TypeError("Subclass of PhyllException must define `detail`")
        
        self.detail = detail if detail is not None else getattr(self.__class__, "detail")
        self.status_code = status_code if status_code is not None else getattr(self.__class__, "status_code")
        # attach extra context fields (e.g., cart_id, user_id)
        for key, value in kwargs.items():
            setattr(self, key, value)

DetailFn = Callable[[PhyllException], Any]

class BadRequest(PhyllException):
    status_code = 400
    detail = "Bad request"

def create_exception_handler(detail_fn: DetailFn) -> Callable[[Request, PhyllException], Any]:
    async def exception_handler(request: Request, exc: PhyllException):
        return JSONResponse(
            content={
                "status": "error",
                "data": None,
                "error": {"details": detail_fn(exc),"code": str(exc.status_code)},
            },
            status_code=getattr(exc, "status_code"),
        )
    return exception_handler

async def http_exception_handler(request: Request, exc: HTTPException):
    details = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    code = getattr(exc,"status_code")
    # message = detail.get("message", str(detail.get("message", exc.detail)))
    # details = detail.get("details")
    payload = build_error(code=code, details=details, trace_id=None)
    return JSONResponse(payload, status_code=code)

async def fallback_handler(request: Request, exc: Exception):
    
    body = {
        "detail": "Internal Server Error from fallback exception handler",
        "error_type": type(exc).__name__
    }

    logger.debug(f"{exc} fallback handler error occured ")
    
    code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
    payload = build_error(code=code, details=body, trace_id=None)
    return JSONResponse(status_code=code, content=payload)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    #* log in logger
    payload = build_error(code=status.HTTP_422_UNPROCESSABLE_ENTITY, details=exc.errors(), trace_id=None)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=payload
    )


def register_all_exceptions(app: FastAPI):

    # mapping : list [tuple[Type[PhyllException],DetailFn]]=[
    #     (BadRequest, lambda exc: {"detail": exc.detail})     
    # ]

    # for exc_class,fn in mapping:
    #     app.add_exception_handler(exc_class,create_exception_handler(fn))

    app.add_exception_handler(
        HTTPException,
        http_exception_handler)

    app.add_exception_handler(
        Exception, # catch all unidentified/unhandled exceptions
        fallback_handler
    )

    app.add_exception_handler(
        RequestValidationError, # catch all unidentified/unhandled exceptions
        validation_exception_handler
    )