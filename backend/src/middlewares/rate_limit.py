"""限流中间件：Redis 固定窗口；采集/导出等写接口单独额度。"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.config.settings import settings
from src.constants.limits import RATE_WINDOW_SECONDS
from src.utils.logger import get_logger

logger = get_logger("rate_limit")
SKIP_PATHS = {"/api/health", "/health"}
# 写接口单独额度。注意：Nginx 反代会把 /api 前缀剥掉（location /api/ -> proxy_pass …/），
# 因此统一按「去掉 /api 之后的路径」匹配；否则经前端代理进来的写请求全部落进默认读桶，
# RATE_LIMIT_WRITE_PER_MINUTE 在线上等于没生效（写接口可被无限连打）。
WRITE_BUCKET_PREFIXES = ("/ingest-runs", "/sources", "/flags", "/clusters", "/listings")


def _normalized_path(path: str) -> str:
    """剥掉 /api 前缀，兼容后端直连（带 /api）与 Nginx 反代（不带 /api）两种入口。"""
    if path.startswith("/api/"):
        return path[len("/api"):]
    return path


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        raw_path = request.url.path
        if raw_path in SKIP_PATHS:
            return await call_next(request)
        path = _normalized_path(raw_path)
        try:
            import redis

            client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
            is_write = request.method in {"POST", "PATCH", "PUT", "DELETE"} and path.startswith(
                WRITE_BUCKET_PREFIXES
            )
            limit = settings.rate_limit_write_per_minute if is_write else settings.rate_limit_per_minute
            scope = "write" if is_write else "default"
            ip = request.client.host if request.client else "unknown"
            window = int(time.time() // RATE_WINDOW_SECONDS)
            key = f"rentlens:rl:{scope}:{ip}:{window}"
            count = client.incr(key)
            if count == 1:
                client.expire(key, RATE_WINDOW_SECONDS + 2)
            if count > limit:
                return JSONResponse(
                    status_code=429,
                    content={
                        "code": "RATE_LIMITED",
                        "message": "请求过于频繁，请稍后再试",
                        "detail": {"limit": limit, "scope": scope},
                    },
                )
        except Exception as exc:  # noqa: BLE001 - 限流降级，不影响主流程
            logger.debug("rate limit degraded: %s", exc)
        return await call_next(request)
