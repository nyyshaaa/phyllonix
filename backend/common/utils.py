
from datetime import datetime,timezone
from typing import Any, Dict, Optional, Union

from fastapi import Request
from fastapi.responses import JSONResponse

def now() -> datetime:
    return datetime.now(timezone.utc)


def build_success(data: Dict[str, Any],
                  trace_id: Optional[str] = None,request_id: Optional[str] = None,) -> Dict[str, Any]:
    return {
        "status": "ok",
        "data": data,
        "error": None,
        "trace_id": trace_id,
        "request_id": request_id,
    }

def build_error(code: Union[str, int] = "UNKNOWN_ERROR",
                details: Optional[Any] = None,
                request_id: Optional[str] = None,
                trace_id: Optional[str] = None) -> Dict[str, Any]:
   
    return {
        "status": "error",
        "data": None,
        "error": {"code": code, "details": details},
        "trace_id": trace_id,
        "request_id": request_id,
    }

def json_ok(content: Dict[str, Any], status_code: int = 200,headers = None) -> JSONResponse:
    return JSONResponse(content, status_code=status_code,headers=headers)

def json_error(content: Dict[str, Any], status_code: int = 500, headers=None) -> JSONResponse:
    return JSONResponse(content, status_code=status_code, headers=headers)

def success_response(data: Dict[str, Any], status_code: int = 200,headers: Optional[Dict[str, Any]] = None , 
                     trace_id: Optional[str] = None , request_id: Optional[str] = None) -> JSONResponse:
    content = build_success(data, request_id=request_id, trace_id=trace_id)
    return json_ok(content, status_code=status_code,headers=headers)

def get_trace_id_from_request(request: Request) -> Optional[str]:
    return getattr(request.state, "trace_id", None)