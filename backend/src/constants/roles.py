"""角色 -> 权限点映射。README 与前端 constants/roles.ts 同步。"""
from __future__ import annotations

from src.constants.enums import Role

ROLE_LABELS: dict[str, str] = {
    Role.ADMIN.value: "研究组长",
    Role.ANALYST.value: "数据专员",
    Role.CLIENT.value: "中介客户（只读）",
}

ROLE_DUTIES: dict[str, str] = {
    Role.ADMIN.value: "维护采集源与阈值、复核价格工单、导出行情周报、查看审计",
    Role.ANALYST.value: "跑采集、复核工单、修正挂牌单价",
    Role.CLIENT.value: "只读行情与核验进度，看不到原始联系方式",
}

PERMISSIONS: dict[str, set[str]] = {
    Role.ADMIN.value: {
        "listing:read", "listing:write", "source:read", "source:write",
        "ingest:read", "ingest:run", "cluster:read", "cluster:recompute",
        "flag:read", "flag:review", "export:read", "audit:read", "contact:read",
    },
    Role.ANALYST.value: {
        "listing:read", "listing:write", "source:read",
        "ingest:read", "ingest:run", "cluster:read", "cluster:recompute",
        "flag:read", "flag:review", "contact:read",
    },
    Role.CLIENT.value: {"listing:read", "cluster:read", "flag:read"},
}

# route 层使用的角色白名单（真实 HTTP 403 的判定依据）
READ_ROLES = (Role.ADMIN.value, Role.ANALYST.value, Role.CLIENT.value)
# 采集源配置与运行记录属于内部信息，中介客户不可读
SOURCE_READ_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
LISTING_WRITE_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
SOURCE_WRITE_ROLES = (Role.ADMIN.value,)
INGEST_RUN_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
REVIEW_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
CLUSTER_WRITE_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
EXPORT_ROLES = (Role.ADMIN.value,)
AUDIT_ROLES = (Role.ADMIN.value,)
# 能看到原始联系方式（电话）的角色
CONTACT_ROLES = (Role.ADMIN.value, Role.ANALYST.value)


def has_permission(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())


def can_see_contact(role: str) -> bool:
    return role in CONTACT_ROLES
