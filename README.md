# rentlens · 二手房挂牌采集与虚高报价核验台

**一句话**：把「5 个平台重复挂牌 → 人工 Excel 去重 → 拍脑袋算均价」这条链，换成可复核的采集 / 指纹去重 / 稳健 z 检验 / 工单复核 / 行情导出闭环。

---

## 1. 真实场景

| 项 | 内容 |
|---|---|
| 模拟客户 | 安家数据服务 · 楼盘研究组（8 人），为 3 家本地中介做挂牌行情与外呼名单 |
| 现有工作流 | 每天 08:30 从 5 个平台（链家式聚合站 / 安居式信息港 / 业主论坛 / 中介朋友圈存档 / 门店群公告）抓挂牌；研究助理把「小区 / 户型 / 面积 / 楼层 / 总价 / 单价 / 挂牌日」抄进 Excel，人工挑重复房源，再算小区均价 |
| 三个痛点 | ① 同一套房在 3-4 个平台重复挂牌，均价被抬高；② 明显虚高（试探价/钓鱼价）与虚低（引流价）混进均值；③ 采集失败、字段缺失要到晚上出周报才发现 |
| 上下游 | 上游＝5 个平台列表页与详情页（**确定性 fixture**，含分页与 429 限流）；本台替代「人工抄录 + Excel 去重 + 拍脑袋均价」；下游＝中介客户的行情周报与推荐名单 |
| 角色 | `admin` 研究组长（源/阈值/复核/导出/审计）｜`analyst` 数据专员（跑采集、复核、修正单价）｜`client` 中介客户（只读行情，不含原始联系方式） |

### 一天的工作剧本（seed 数据与之一致）

1. **08:30** 定时任务（Celery beat）跑 `rentlens.scheduled_ingest`，5 个平台分页抓取，安居第 3 页与朋友圈第 2 页各命中一次 429，按 800ms → 1600ms 退避后重试成功。
2. **08:31** 240 条挂牌入库（按 `source_id + 挂牌编号` upsert），其中 3 条面积缺失，标 `unknown` 不进均价。
3. **08:32** 指纹去重：规范化 + 小区×户型 blocking + 加权相似（面积 .30 / 楼层 .20 / 标题 Jaccard .25 / 单价接近 .25）+ 并查集，阈值 0.82 → **32 组重复、78 条重复挂牌、去重后 194 套**。
4. **08:33** 均价刷新：`兰亭苑 三居` 去重前 **61,200 元/㎡**（42 条含重复）→ 去重后 **58,900 元/㎡**（28 套主房源）。
5. **08:34** 稳健 z：8 个小区×户型分组各 ≥8 套，`阳光里 两居` 一套 79,072 元/㎡ 的钓鱼价偏离中位 **41.2%**、**z=4.31**，判 `high`；整批产出 **12 个工单（7 高 / 3 低 / 2 待确认）**。
6. **09:10** 数据专员在核验队列确认 3 个虚高、驳回 1 个引流价，备注写进审计。
7. **09:20** 门店回价：把 `兰亭苑 三居` 一套 65,686 元/㎡ 修正为 63,900，触发该批次中位/MAD 与工单重算。
8. **09:30** 研究组长导出行情 CSV（194 行，含簇成员数、跨平台数、偏离、z、复核态），发周报。
9. **10:00** 组长在「采集源与运行」把门店群公告的节奏从 hourly 改成 twice_daily，写审计。
10. **周复盘** 打开审计日志核对「谁改了什么价、谁确认了哪个虚高」。

---

## 2. 主要功能

| 模块 | 页面 | 关键能力 |
|---|---|---|
| 登录 / 鉴权 | `/login` | JWT + 三角色；密码 `Demo@2026`；低权角色调高权接口真实 403 |
| 采集运行 | `/sources` | 5 个源分页抓取、429 指数退避、逐源结果、运行记录、只重算去重 |
| 挂牌池 | `/listings` | 重复标记、单价排序、小区/户型/来源/标记筛选、去重后口径切换、分页 |
| 房源详情 | `/listings/:id` | 多平台并排对比 + 簇内相似度 + 价格序列 SVG + 小区×户型 均价口径（去重前/后） |
| 核验队列 | `/flags` | 虚高/虚低/待确认分栏、偏离条、稳健 z、置信度、一键确认/驳回、导出 |
| 行情导出 | `/flags`、API | `GET /api/exports/market.csv`，去重后主房源口径，194 行 |

### 两个真算算法（全部在 Python 后端，前端不含任何硬编码结果）

**算法 1 · 房源指纹去重**（`backend/src/services/fingerprint_service.py` + `backend/src/utils/similarity.py`）

1. 规范化：小区别名表（`兰亭苑小区 → 兰亭苑`）、户型别名（`3室2厅 → 三居`）、面积取整到 1㎡、楼层带归一（`中楼层(共18层) → 9`）。
2. blocking key = `小区 × 户型`，只在同组内两两比较，复杂度从 O(n²) 降到组内。
3. 加权相似：`0.30*面积 + 0.20*楼层 + 0.25*标题Jaccard + 0.25*单价接近度`；面积容差 1㎡、楼层容差 4 层、单价容差 8%。
4. 相似度 ≥ **0.82** 连边，并查集（路径压缩 + 按秩合并）聚簇；主房源 = 挂牌最早 → 字段最全 → id 最小。
5. 输出：簇、主房源、成员相似度摘要、跨平台数；面积缺失的挂牌不参与连边（单独成簇，不进均价）。
6. 失败态：同组无候选 → 独占一簇；样本面积全缺失 → 该组均价为 `null`（前端显示「面积缺失，不计均价」）。

**算法 2 · 虚高/虚低检测**（`backend/src/services/price_service.py`）

- 按 `小区 × 户型` 分组，**样本 ≥ 8 套**才判定（不足标 `unknown`，不做结论）。
- `med = 中位单价`，`MAD = median(|x_i − med|)`，`z = 0.6745 × (x − med) / MAD`。
- `|z| > 3` **且** `|偏离中位| > 30%` → `high` / `low`；`25% < |偏离| ≤ 30%` → `uncertain`（边界样本进人工）。
- 置信度 = `0.40×样本量分 + 0.35×|z|分 + 0.25×字段完整度`（样本 40 套、|z|=6 为满分）。
- 可复现：分组样本来自确定性 fixture（`backend/fixtures/platforms.json`），同输入同输出，无随机数。

---

## 3. 快速启动

```bash
cp .env.example .env
docker compose up -d --build
# 等 5/5 healthy（首次构建约 2-4 分钟）
docker compose ps
```

| 入口 | 地址 |
|---|---|
| 前端（挂牌池 / 核验 / 采集源） | http://localhost:18250 |
| 后端 OpenAPI | http://localhost:19250/docs |
| 健康检查 | http://localhost:19250/api/health |
| MySQL | `127.0.0.1:17750`（库/用户/密码见 `.env`） |

seed 在 backend 首次启动时自动执行（`SEED_DEMO=true`），也可以手动重跑（幂等）：

```bash
docker compose exec backend python -m scripts.seed_demo
# SEED_SUMMARY brand=rentlens sources=5 listings=240 clusters=32 flags=12 users=3
```

**演示账号**（密码统一 `Demo@2026`）

| 邮箱 | 角色 | 能做什么 | 不能做什么（真实 403） |
|---|---|---|---|
| `admin@rentlens.io` | 研究组长 | 改采集源、跑采集、复核、修单价、导出行情 CSV、看审计 | — |
| `analyst@rentlens.io` | 数据专员 | 跑采集、复核工单、修单价 | `POST/PATCH /api/sources`（改源配置）403、导出 CSV 403 |
| `client@rentlens.io` | 中介客户（只读） | 看挂牌池、房源详情、核验队列 | `POST /api/ingest-runs` 403、`PATCH /api/flags/{id}` 403、`GET /api/exports/market.csv` 403、`GET /api/sources` 与 `GET /api/ingest-runs` 403（采集运行属内部信息）；接口返回里 `agent_contact` 为 `null` |

**本地开发**

```bash
# 后端
cd backend && python3.11 -m venv .venv && . .venv/bin/activate
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
DB_HOST=127.0.0.1 DB_PORT=17750 PYTHONPATH=. uvicorn src.main:app --port 8000

# 前端
cd frontend && npm install --registry=https://registry.npmmirror.com && npm run dev
# vite 代理 /api -> http://localhost:19250
```

---

## 4. 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React 18 + TypeScript + Vite 5 + React Router 6，SVG 自绘图表（无图表库 / 无 CDN） |
| 后端 | Python 3.11 + FastAPI + SQLAlchemy 2.0 + Pydantic v2 + PyJWT + passlib(bcrypt) |
| 异步 | Celery 5.4 + Redis 7（心跳、08:30 定时采集、重算任务） |
| 数据库 | MySQL 8.0（utf8mb4） |
| 网关 | Nginx 1.27（`/api/` 反代 + SPA 回落） |
| 容器 | Docker Compose：frontend / backend / worker / db / redis，全部带 healthcheck |

---

## 5. 目录结构

```
gb-577/
├── docker-compose.yml            # 5 服务 + 5 healthcheck + 命名卷
├── .env / .env.example
├── backend/
│   ├── Dockerfile  requirements.txt  migrations/
│   ├── fixtures/                 # 5 个平台的确定性页面快照 + 生成器
│   │   ├── generate_fixtures.py  # 离线一次性运行，产物 platforms.json / sources.json
│   │   ├── platforms.json        # 240 条挂牌、分页、429 页
│   │   └── sources.json
│   ├── scripts/{seed_demo,demo_config,worker_healthcheck.sh}
│   └── src/
│       ├── config/               # settings / database / celery_app / app
│       ├── constants/            # enums / roles / limits（算法阈值）/ error_codes / log_templates
│       ├── models/               # user audit source listing cluster price_flag ingest_run block_stat
│       ├── schemas/              # auth source listing cluster price_flag ingest common
│       ├── services/             # fetch parsers fingerprint price cluster ingest listing source flag export audit overview
│       ├── controllers/          # auth source listing cluster flag ingest export overview
│       ├── routes/               # health auth overview sources listings clusters flags ingest_runs exports audit
│       └── middlewares/          # auth / audit_logger / rate_limit / error_handler / rbac
└── frontend/
    ├── Dockerfile  nginx.conf  vite.config.ts  tsconfig.json
    └── src/
        ├── api/                  # client auth overview sources listings clusters flags ingest exports
        ├── stores/               # auth ui listings clusters flags sources
        ├── hooks/                # useAsync useFilters(useDebouncedValue) useToast
        ├── components/common/    # LedgerTable StampTag PriceSeriesChart MetricStrip FilterBar EmptyState ErrorState Toasts
        ├── components/layout/    # AppShell
        ├── pages/                # Login Listings ListingDetail Sources Flags
        ├── router/               # index + guards
        ├── constants/            # enums roles ui
        ├── types/  utils/  styles/
```

---

## 6. 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | `rentlens` | 容器名前缀 `${COMPOSE_PROJECT_NAME}-<role>` |
| `FRONTEND_PORT` | `18250` | Nginx 80 映射 |
| `BACKEND_PORT` | `19250` | uvicorn 8000 映射 |
| `DB_PORT` | `17750` | MySQL 3306 映射 |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | `rentlens` / `rentlens` / `rentlens_pw_2026` | MySQL 库与账号 |
| `DB_ROOT_PASSWORD` | `rentlens_root_2026` | root 密码 |
| `JWT_SECRET` | `rentlens-jwt-secret-change-me-2026` | HS256 密钥，**生产必须换** |
| `REDIS_URL` | `redis://redis:6379/0` | Celery broker/backend + 限流 + 心跳 |
| `SEED_DEMO` | `true` | backend 启动时跑一次 seed（幂等） |
| `RATE_LIMIT_PER_MINUTE` | `300` | 读接口固定窗口额度 |
| `RATE_LIMIT_WRITE_PER_MINUTE` | `60` | 写接口额度（采集/复核/改价等） |
| `APP_TIMEZONE_OFFSET_MINUTES` | `480` | 业务时区 UTC+8 |
| `CRAWL_BACKOFF_BASE_MS` | `800` | 429 退避基数（指数 2ⁿ，上限 4s） |

---

## 7. Docker 说明

- 5 个服务全部有 healthcheck：db(`mysqladmin ping`) / redis(`redis-cli ping`) / backend(`urllib` 打 `/api/health`) / worker(`worker_healthcheck.sh` 读心跳或 celery ping) / frontend(`wget --spider`)。
- 依赖关系用 `service_healthy` 串起来：backend、worker ← db+redis；worker 额外等 backend；frontend ← backend。
- 命名卷：`db_data`、`redis_data`。
- 前端镜像内 `npm install` 默认走 `registry.npmmirror.com`，可用 `--build-arg NPM_REGISTRY=https://registry.npmjs.org` 覆盖；后端 pip 走清华源。
- 收尾：`docker compose down -v --remove-orphans`（会清掉演示库，便于复现）。

---

## 8. 共享枚举出现位置（前后端各一份，改一侧必须同步另一侧）

| 枚举 | 后端定义 | 后端使用 | 前端定义 | 前端使用 |
|---|---|---|---|---|
| `Role`（admin/analyst/client） | `backend/src/constants/enums.py` | `constants/roles.py`（权限表）、`middlewares/rbac.py`、`models/user.py`、`routes/*` | `frontend/src/constants/enums.ts` | `constants/roles.ts`、`router/guards.tsx`、`components/layout/AppShell.tsx`、`pages/*` |
| `FlagType`（high/low/uncertain） | 同上 | `services/price_service.py`、`services/cluster_service.py`、`services/flag_service.py`、`schemas/price_flag.py` | 同上 + `FLAG_TYPE_LABELS` | `pages/Flags.tsx`、`pages/Listings.tsx`、`pages/ListingDetail.tsx`、`components/common/StampTag.tsx` |
| `ReviewStatus`（pending/confirmed/dismissed） | 同上 | `services/flag_service.py`、`services/cluster_service.py`、`services/export_service.py` | 同上 + `REVIEW_LABELS` | `pages/Flags.tsx`、`pages/ListingDetail.tsx` |
| `IngestStatus`（running/success/partial/failed） | 同上 | `services/ingest_service.py`、`models/ingest_run.py`、`scripts/seed_demo.py` | 同上 + `INGEST_STATUS_LABELS` | `pages/Sources.tsx` |
| `PlatformKind`（aggregator/portal/forum/moments/notice） | 同上 | `services/parsers.py`、`services/source_service.py`、`fixtures/sources.json` | 同上 + `PLATFORM_LABELS` | `pages/Sources.tsx` |
| `Layout` / `FloorBand` | 同上 | `services/parsers.py`、`utils/similarity.py` | 同上 | `pages/Listings.tsx`、`pages/ListingDetail.tsx` |

算法阈值集中在 `backend/src/constants/limits.py`（前端只展示，不参与判定）。

---

## 9. 横切能力

- **JWT + 角色**：`middlewares/auth.py` 解析 token → `middlewares/rbac.py` 的 `require_roles` 抛 401/403；前端 `REQUEST` 层在 401 时清登录态。
- **审计日志**：`middlewares/audit_logger.py` 记 HTTP 写请求（layer=http）；controller 再记领域动作（登录、跑采集、改源、复核、改价、导出、重算）。`GET /api/audit-logs` 仅 admin。
- **限流**：`middlewares/rate_limit.py` Redis 固定窗口，读 300/min、写 60/min，超限 429 `RATE_LIMITED`。
- **全局错误处理**：`middlewares/error_handler.py` 统一 `{code,message,detail}`；前端 `ErrorState` 按 code/status 给出可恢复动作。

---

## 10. License

MIT（演示项目，fixture 与公司名均为虚构）。
