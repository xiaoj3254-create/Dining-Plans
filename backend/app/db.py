import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

engine = None
SessionLocal = None


def _make_engine(db_url: str):
    eng = create_engine(db_url, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return eng


def init_db(db_url: str | None = None):
    """初始化（或重置，供测试使用）全局 engine / SessionLocal 并建表"""
    global engine, SessionLocal
    url = db_url or os.environ.get("DP_DATABASE_URL", "sqlite:///./dining_plans.db")
    if engine is not None:
        engine.dispose()
    engine = _make_engine(url)
    # autoflush=True：链式副作用内的 SELECT 必须能看到同事务待插入的行（如最后一名成员）
    SessionLocal = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)

    from app import models  # noqa: F401  确保所有模型已注册

    Base.metadata.create_all(engine)
    return engine
