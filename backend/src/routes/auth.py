from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers import auth_controller
from src.middlewares.rbac import principal_of
from src.schemas.auth import LoginIn, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)) -> dict:
    return auth_controller.login(db, payload.email, payload.password, request)


@router.get("/me")
def me(principal: dict = Depends(principal_of), db: Session = Depends(get_db)) -> dict:
    return auth_controller.me(db, principal["email"])
