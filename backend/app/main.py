import asyncio
from contextlib import asynccontextmanager, suppress
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .attachment_service import cleanup_attachment_storage
from .config import get_settings, validate_production_settings
from .db import Base, SessionLocal, engine
from .routers import admin, auth, builds, dashboard, files, statistics, wkd
from .seed import seed

settings = get_settings()
validate_production_settings(settings)
logger = logging.getLogger(__name__)


def run_attachment_cleanup() -> None:
    try:
        with SessionLocal() as db:
            locked = False
            if db.bind.dialect.name == 'postgresql':
                from sqlalchemy import text
                locked = bool(db.scalar(text('SELECT pg_try_advisory_lock(827364501)')))
                if not locked:
                    return
            try:
                result = cleanup_attachment_storage(db)
            finally:
                if locked:
                    db.rollback()
                    db.execute(text('SELECT pg_advisory_unlock(827364501)'))
                    db.commit()
        if any(result.values()):
            logger.info('附件清理完成：%s', result)
    except Exception:
        logger.exception('附件清理任务失败，将在下个周期重试')


async def attachment_cleanup_loop() -> None:
    while True:
        await asyncio.to_thread(run_attachment_cleanup)
        await asyncio.sleep(settings.attachment_cleanup_interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    # 当前项目尚未引入 Alembic；启动时以幂等方式补充本次新增列和索引。
    from sqlalchemy import text
    with engine.begin() as connection:
        connection.execute(text("ALTER TYPE wkdstatus ADD VALUE IF NOT EXISTS 'DISABLE_CONFIRM'"))
        connection.execute(text('ALTER TABLE wkd_history ADD COLUMN IF NOT EXISTS changes JSONB'))
        connection.execute(text('ALTER TABLE wkds ADD COLUMN IF NOT EXISTS current_handler_id VARCHAR(36) REFERENCES users(id)'))
        connection.execute(text('ALTER TABLE wkds ADD COLUMN IF NOT EXISTS creation_key VARCHAR(64)'))
        connection.execute(text('ALTER TABLE wkds ADD COLUMN IF NOT EXISTS creation_hash VARCHAR(64)'))
        connection.execute(text('ALTER TABLE users ADD COLUMN IF NOT EXISTS global_role_id VARCHAR(36) REFERENCES roles(id) ON DELETE RESTRICT'))
        connection.execute(text('ALTER TABLE users ADD COLUMN IF NOT EXISTS department VARCHAR(120)'))
        connection.execute(text('ALTER TABLE users DROP COLUMN IF EXISTS name'))
        connection.execute(text('ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_key'))
        connection.execute(text('DROP INDEX IF EXISTS users_username_key'))
        connection.execute(text('ALTER TABLE attachments ADD COLUMN IF NOT EXISTS upload_session_id VARCHAR(36) REFERENCES upload_sessions(id) ON DELETE SET NULL'))
        connection.execute(text("ALTER TABLE attachments ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'READY'"))
        connection.execute(text('ALTER TABLE attachments ADD COLUMN IF NOT EXISTS multipart BOOLEAN NOT NULL DEFAULT FALSE'))
        connection.execute(text('ALTER TABLE attachments ADD COLUMN IF NOT EXISTS storage_upload_id VARCHAR(255)'))
        connection.execute(text('ALTER TABLE attachments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP'))
        connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_wkd_creation_key ON wkds(creation_key) WHERE creation_key IS NOT NULL'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS ix_attachments_upload_session_id ON attachments(upload_session_id)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS ix_attachments_status ON attachments(status)'))
        connection.execute(text("UPDATE wkds SET current_handler_id = owner_id WHERE current_handler_id IS NULL AND status IN ('NEW_WKD', 'VERIFY')"))
    with SessionLocal() as db:
        seed(db)
    cleanup_task = asyncio.create_task(attachment_cleanup_loop()) if settings.attachment_cleanup_enabled else None
    yield
    if cleanup_task:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task

app = FastAPI(title=settings.app_name, version='1.8.0', lifespan=lifespan,
    description='WKD 全生命周期、原子操作编排、项目级 RBAC、构建制品和 RustFS 文件接口。除认证与健康检查外，所有接口均需 Bearer Token，并在服务端执行按钮权限校验。',
    docs_url='/docs', redoc_url='/redoc', openapi_url='/openapi.json')
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
                   allow_methods=['*'], allow_headers=['*'])
app.include_router(auth.router, prefix='/api/v1')
app.include_router(dashboard.router, prefix='/api/v1')
app.include_router(statistics.router, prefix='/api/v1')
app.include_router(wkd.router, prefix='/api/v1')
app.include_router(builds.router, prefix='/api/v1')
app.include_router(files.router, prefix='/api/v1')
app.include_router(admin.router, prefix='/api/v1')

@app.get('/health', tags=['系统'], summary='服务健康检查')
def health():
    return {'status': 'ok', 'service': 'wmp-api', 'version': '1.8.0'}
