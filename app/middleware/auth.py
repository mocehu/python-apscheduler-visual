"""
API Key 认证中间件
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


PUBLIC_PATHS = [
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
]

AI_PATHS = [
    "/ai/chat",
    "/ai/chat/stream",
    "/ai/sessions",
    "/ai/models",
    "/ai/tools",
    "/ai/config",
]


def _get_auth_config():
    """获取认证配置"""
    from app.core.conf import API_KEY, API_KEY_ENABLED
    
    if not API_KEY_ENABLED:
        return False, API_KEY, ""
    
    try:
        from app.core.database import _session_factory, get_config_bool, get_config
        db = _session_factory()
        try:
            enabled = get_config_bool(db, "api_key_enabled", True)
            key = get_config(db, "api_key", API_KEY)
            agent_key = get_config(db, "ai_agent_api_key", "")
            return enabled, key, agent_key
        finally:
            db.close()
    except Exception:
        return True, API_KEY, ""


def _is_ai_path(path: str) -> bool:
    """检查是否为 AI 相关路径"""
    for ai_path in AI_PATHS:
        if path == ai_path or path.startswith(ai_path + "/"):
            return True
    return False


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        auth_enabled, api_key, agent_api_key = _get_auth_config()
        
        if not auth_enabled:
            return await call_next(request)
        
        path = request.url.path
        
        if path in PUBLIC_PATHS:
            return await call_next(request)
        
        for public_path in PUBLIC_PATHS:
            if path.startswith(public_path):
                return await call_next(request)
        
        request_api_key = request.headers.get("X-API-Key")
        
        if not request_api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "code": 401,
                    "msg": "未授权：缺少 API Key",
                    "data": None
                }
            )
        
        if _is_ai_path(path) and agent_api_key and request_api_key == agent_api_key:
            return await call_next(request)
        
        if request_api_key != api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "code": 401,
                    "msg": "未授权：无效的 API Key",
                    "data": None
                }
            )
        
        return await call_next(request)
