# migrations

运行时表结构由 SQLAlchemy `Base.metadata.create_all` 在 backend 启动时创建（演示项目不引入 Alembic）。

- `0001_initial.sql`：与 `src/models/*` 一一对应的等价 DDL，供 DBA 预审索引与走正式迁移流程。
- `ingest_runs.trigger_kind` 对应模型里的 `IngestRun.trigger_kind`（不叫 `trigger`，避开 MySQL 保留字）。
