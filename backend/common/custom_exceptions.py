from collections.abc import Callable
from typing import Any, Type, Union
from fastapi import FastAPI, Request,status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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
            status_code=getattr(exc, "status_code"),
            content=detail_fn(exc),
        )
    return exception_handler

async def fallback_handler(request: Request, exc: Exception):
    
    body = {
        "detail": getattr(exc, "detail", "Internal Server Error from fallback exception handler"),
        "error_type": type(exc).__name__
    }
    
    code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
    print("falback exception")
    return JSONResponse(status_code=code, content=body)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    #* log in logger
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation failed",
            "detail": exc.errors(),
        },
    )


def register_all_exceptions(app: FastAPI):

    mapping : list [tuple[Type[PhyllException],DetailFn]]=[
        (BadRequest, lambda exc: {"detail": exc.detail})     
    ]

    for exc_class,fn in mapping:
        app.add_exception_handler(exc_class,create_exception_handler(fn))

    app.add_exception_handler(
        Exception, # catch all unidentified/unhandled exceptions
        fallback_handler
    )

    app.add_exception_handler(
        RequestValidationError, # catch all unidentified/unhandled exceptions
        validation_exception_handler
    )