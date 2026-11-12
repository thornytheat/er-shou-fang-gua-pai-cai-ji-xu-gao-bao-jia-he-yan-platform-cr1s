"""演示数据配置：3 个账号 / 3 条历史采集运行 / 2 条审计（与 README 的剧本一致）。"""
from __future__ import annotations

DEMO_PASSWORD = "Demo@2026"

# (email, display_name, role)
DEMO_USERS = [
    ("admin@rentlens.io", "沈砚（研究组长）", "admin"),
    ("analyst@rentlens.io", "许清（数据专员）", "analyst"),
    ("client@rentlens.io", "安家地产 · 王经理（中介客户）", "client"),
]

# 历史运行（相对今天的偏移天数，条数，限流次数，状态，摘要）
HISTORY_RUNS = [
    ("seed:run:2026-11-08", "2026-11-08T08:30:12", 5, 58, 238, 2, 1600, "success",
     "采集 238 条，写入 238 条（4 个平台分页正常）"),
    ("seed:run:2026-11-09", "2026-11-09T08:30:09", 5, 60, 240, 2, 1600, "success",
     "采集 240 条，写入 240 条"),
    ("seed:run:2026-11-10", "2026-11-10T08:30:15", 5, 60, 240, 2, 1600, "partial",
     "门店群公告第 4 页超时，其余 4 个源完整"),
]

SEED_AUDIT = [
    ("seed:audit:1", "admin@rentlens.io", "admin", "source.update", "source", "1",
     {"frequency": "daily 08:30", "rate_limit_per_min": 60}),
    ("seed:audit:2", "analyst@rentlens.io", "analyst", "flag.review", "price_flag", "3",
     {"review_status": "confirmed", "flag_type": "high", "note": "业主确认是试探价"}),
]

# 团队信息（前端登录页展示）
TEAM = {
    "name": "安家数据服务 · 楼盘研究组",
    "size": 8,
    "clients": 3,
    "routine": "每天 08:30 从 5 个平台抓挂牌，人工抄进 Excel 再去重算均价",
}
