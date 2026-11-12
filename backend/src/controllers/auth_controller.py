"""认证控制器。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, auth_service
from src.utils.errors import AppError


def login(db: Session, email: str, password: str, request: Request) -> dict:
    try:
        result = auth_service.login(db, email, password)
    except auth_service.AuthError as exc:
        raise AppError(exc.code, exc.status_code) from exc
    audit_service.record(
        db,
        actor_email=result["user"]["email"],
        actor_role=result["user"]["role"],
        action="auth.login",
        entity="user",
        entity_id=result["user"]["id"],
        detail={"role": result["user"]["role"]},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return result


def me(db: Session, email: str) -> dict:
    user = auth_service.get_user_by_email(db, email)
    if user is None:
        raise AppError("AUTH_MISSING", 401)
    return {"user": auth_service.serialize_user(user)}
