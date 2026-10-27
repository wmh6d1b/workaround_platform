from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import get_settings
from .db import Base, SessionLocal, engine
from .routers import admin, auth, builds, dashboard, files, statistics, wkd
from .seed import seed

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    # 当前项目尚未引入 Alembic；启动时以幂等方式补充本次新增列。
    from sqlalchemy import text
    with engine.begin() as connection:
        connection.execute(text("ALTER TYPE wkdstatus ADD VALUE IF NOT EXISTS 'DISABLE_CONFIRM'"))
        connection.execute(text('ALTER TABLE wkd_history ADD COLUMN IF NOT EXISTS changes JSONB'))
        connection.execute(text('ALTER TABLE wkds ADD COLUMN IF NOT EXISTS current_handler_id VARCHAR(36) REFERENCES users(id)'))
        connection.execute(text('ALTER TABLE users ADD COLUMN IF NOT EXISTS global_role_id VARCHAR(36) REFERENCES roles(id) ON DELETE RESTRICT'))
        connection.execute(text("UPDATE wkds SET current_handler_id = owner_id WHERE current_handler_id IS NULL AND status IN ('NEW_WKD', 'VERIFY')"))
    with SessionLocal() as db:
        seed(db)
    yield

app = FastAPI(title=settings.app_name, version='1.4.0', lifespan=lifespan,
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
    return {'status': 'ok', 'service': 'wmp-api', 'version': '1.4.0'}
