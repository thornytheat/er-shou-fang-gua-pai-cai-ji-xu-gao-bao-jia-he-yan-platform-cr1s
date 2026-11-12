"""算法口径与运行约束常量（口径集中，禁止散落在 service 里）。

两个真算算法的全部阈值都在这里，README「算法口径」一节与前端只读展示。
"""
from __future__ import annotations

# ---------- 算法 1：房源指纹去重 ----------
# 加权相似度权重：面积 0.30 / 楼层 0.20 / 标题 Jaccard 0.25 / 单价接近度 0.25
SIM_WEIGHTS: dict[str, float] = {
    "area": 0.30,
    "floor": 0.20,
    "title": 0.25,
    "price": 0.25,
}
# 面积容差（㎡）：挂牌页面积已取整到 1㎡，差 1㎡ 仍有部分相似
AREA_TOL_SQM = 1.0
# 楼层容差（层）：差 1 层扣 1/4，差 4 层及以上视为不同房源
FLOOR_TOL = 4.0
# 单价接近度容差（相对均价的百分比）：|Δ|/8% 线性衰减
PRICE_TOL_PCT = 0.08
# 连边阈值：相似度 ≥ 0.82 视为同一套房
SIM_THRESHOLD = 0.82

# ---------- 算法 2：小区×户型 稳健 z 检验 ----------
# 样本量下限：不足 8 条不做判定（样本太小的 z 值不可信）
MIN_SAMPLES_FOR_FLAG = 8
# 稳健 z 阈值
Z_THRESHOLD = 3.0
# 偏离中位数阈值（%）：必须同时越过 z 与偏离才判虚高/虚低
DEV_FLAG_PCT = 30.0
# 边界带（%）：25% < |偏离| ≤ 30% 落「待确认」，交人工判断
DEV_BORDER_PCT = 25.0
# 置信度权重：样本量 0.4 + |z| 0.35 + 字段完整度 0.25
CONFIDENCE_WEIGHTS: dict[str, float] = {"sample": 0.40, "z": 0.35, "completeness": 0.25}
# 置信度满分参考：样本 40 条、|z| = 6
SAMPLE_FULL = 40.0
Z_FULL = 6.0

# ---------- 采集运行 ----------
RATE_WINDOW_SECONDS = 60
# 触发 429 后的最大重试次数（指数退避）
MAX_THROTTLE_RETRIES = 3
# 默认退避基数（毫秒），容器环境变量 CRAWL_BACKOFF_BASE_MS 可覆盖
DEFAULT_BACKOFF_BASE_MS = 800
# 单次采集最多解析多少条（防 fixture 异常把库刷爆）
MAX_ITEMS_PER_RUN = 600
# 运行记录页默认返回条数
RUN_HISTORY_LIMIT = 20
