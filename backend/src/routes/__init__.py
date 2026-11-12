"""路由聚合：统一 /api 前缀（Nginx 反代时剥掉 /api）。"""
from fastapi import APIRouter

from src.routes.audit import router as audit_router
from src.routes.auth import router as auth_router
from src.routes.clusters import router as clusters_router
from src.routes.exports import router as exports_router
from src.routes.flags import router as flags_router
from src.routes.health import router as health_router
from src.routes.ingest_runs import router as ingest_router
from src.routes.listings import router as listings_router
from src.routes.overview import router as overview_router
from src.routes.sources import router as sources_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(overview_router)
api_router.include_router(sources_router)
api_router.include_router(listings_router)
api_router.include_router(clusters_router)
api_router.include_router(flags_router)
api_router.include_router(ingest_router)
api_router.include_router(exports_router)
api_router.include_router(audit_router)
