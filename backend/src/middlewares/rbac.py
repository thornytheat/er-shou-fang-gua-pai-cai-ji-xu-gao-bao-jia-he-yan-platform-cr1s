"""角色鉴权依赖：401 未登录 / 403 角色不足（真实 HTTP 状态码，不是前端隐藏按钮）。"""
from __future__ import annotations

from typing import Callable

from fastapi import Request

from src.constants.roles import PERMISSIONS
from src.utils.errors import AppError


def principal_of(request: Request) -> dict:
    principal = getattr(request.state, "principal", None)
    if not principal:
        raise AppError("AUTH_MISSING", 401)
    return {"email": principal["email"], "role": principal["role"]}


def require_roles(*roles: str) -> Callable[[Request], dict]:
    allowed = set(roles)

    def dependency(request: Request) -> dict:
        principal = principal_of(request)
        if principal["role"] not in allowed:
            raise AppError(
                "FORBIDDEN",
                403,
                detail=f"role={principal['role']} required={','.join(sorted(allowed))}",
            )
        return principal

    return dependency


def require_permission(permission: str) -> Callable[[Request], dict]:
    def dependency(request: Request) -> dict:
        principal = principal_of(request)
        if permission not in PERMISSIONS.get(principal["role"], set()):
            raise AppError("FORBIDDEN", 403, detail=f"permission={permission}")
        return principal

    return dependency
