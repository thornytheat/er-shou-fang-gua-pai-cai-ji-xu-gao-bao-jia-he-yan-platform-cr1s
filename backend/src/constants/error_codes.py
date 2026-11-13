"""统一错误码，前端 utils/errorMessage.ts 兜底文案与之对应。"""
from __future__ import annotations

ERROR_CODES: dict[str, str] = {
    "AUTH_INVALID": "邮箱或密码不正确",
    "AUTH_MISSING": "缺少或无效的访问令牌",
    "FORBIDDEN": "当前角色无权执行该操作",
    "NOT_FOUND": "对象不存在",
    "CONFLICT": "对象状态冲突",
    "RATE_LIMITED": "请求过于频繁，请稍后再试",
    "VALIDATION": "请求参数不合法",
    "SOURCE_DISABLED": "该采集源已停用，无法运行",
    "SOURCE_QUARANTINED": "该来源取数不完整已整源隔离，恢复完整采集前不能操作其挂牌",
    "INGEST_RUNNING": "已有采集任务在运行，请稍候",
    "NO_FIXTURE": "该采集源缺少平台 fixture 目录",
    "NO_SAMPLES": "该小区×户型样本不足 8 条，无法判定",
    "EXPORT_EMPTY": "当前筛选条件下没有可导出的挂牌记录",
    "INTERNAL": "服务内部错误",
}
