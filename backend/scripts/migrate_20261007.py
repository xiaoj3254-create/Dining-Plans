"""2026-10-07 全量审查整改的数据库迁移。

背景：本次整改新增/修改了以下结构，`create_all` 无法覆盖已有表：

- users        + consent_version / consent_at / realname_consent_at / birth_date /
                 report_count / restricted_at / restricted_reason / deleted_at / token_version
- teams        dining_time、target_size、cuisine_type 改为可空；code 加长到 16 位；
                 + failed_at / fail_reason；新增 3 个 CHECK 约束（禁超卖）
- notifications + team_id（结构化，替代 payload 文本反查）+ 复合索引
- messages     + recalled_at（撤回）
- checkins     + checkin_code 唯一索引
- 新表         team_member_events / audit_logs / reports / push_outbox / user_blocks /
                 idempotency_keys

用法（默认 dry-run：只在库副本上跑并打印结论）：
    python scripts/migrate_20261007.py                 # 副本演练
    python scripts/migrate_20261007.py --apply         # 应用到真实库（自动先备份）

幂等：可重复执行（列已存在则跳过，表已重建则跳过）。
"""

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DEFAULT_DB = os.path.join(ROOT, "dining_plans.db")
BACKUP_DIR = os.path.join(ROOT, ".backup")

# 哨兵值：旧实现用 datetime.max 占位"未设置就餐时间"
SENTINEL_PREFIX = "9999-12-31"

USER_COLUMNS = [
    ("consent_version", "VARCHAR(20)"),
    ("consent_at", "DATETIME"),
    ("realname_consent_at", "DATETIME"),
    ("birth_date", "VARCHAR(10)"),
    ("report_count", "INTEGER NOT NULL DEFAULT 0"),
    ("restricted_at", "DATETIME"),
    ("restricted_reason", "VARCHAR(100)"),
    ("deleted_at", "DATETIME"),
    ("token_version", "INTEGER NOT NULL DEFAULT 0"),
]

NOTIFICATION_COLUMNS = [("team_id", "INTEGER")]

MESSAGE_COLUMNS = [("recalled_at", "DATETIME")]


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone()
    return row is not None


def add_columns(conn: sqlite3.Connection, table: str, columns: list[tuple[str, str]],
                log: list[str]) -> None:
    if not _table_exists(conn, table):
        log.append(f"[skip] {table} 不存在")
        return
    have = _cols(conn, table)
    for name, ddl in columns:
        if name in have:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        log.append(f"[add ] {table}.{name}")


def rebuild_teams(conn: sqlite3.Connection, engine, log: list[str]) -> None:
    """重建 teams：改可空 / 加长 code / 新增归因列 / 加 CHECK 约束。

    SQLite 不支持修改列的可空性，只能重建表。注意：
    - 迁移期间关闭外键（checkins/team_members 引用 teams）；
    - 开启 legacy_alter_table，避免 ALTER RENAME 顺带改写其它表的 FK 引用。
    """
    from sqlalchemy.schema import CreateIndex, CreateTable

    from app.models.team import Team

    if _table_exists(conn, "teams_new"):
        conn.execute("DROP TABLE teams_new")

    ddl = str(CreateTable(Team.__table__).compile(engine)).replace(
        "CREATE TABLE teams", "CREATE TABLE teams_new", 1
    )
    conn.execute(ddl)
    log.append("[new ] teams_new（重建表结构）")

    old_cols = _cols(conn, "teams")
    new_cols = [c.name for c in Team.__table__.columns if c.name in old_cols]
    collist = ", ".join(new_cols)
    conn.execute(f"INSERT INTO teams_new ({collist}) SELECT {collist} FROM teams")
    rows = conn.execute("SELECT COUNT(*) FROM teams_new").fetchone()[0]
    log.append(f"[copy] teams → teams_new：{rows} 行")

    conn.execute("DROP TABLE teams")
    conn.execute("ALTER TABLE teams_new RENAME TO teams")
    log.append("[ren ] teams_new → teams")

    for idx in Team.__table__.indexes:
        stmt = str(CreateIndex(idx).compile(engine))
        if _index_exists(conn, idx.name):
            continue
        conn.execute(stmt)
        log.append(f"[idx ] {idx.name}")


def backfill(conn: sqlite3.Connection, log: list[str]) -> None:
    # 1) 清理 datetime.max 哨兵：草稿期"未设置就餐时间"改为 NULL
    n = conn.execute(
        "UPDATE teams SET dining_time = NULL WHERE dining_time LIKE ?",
        (SENTINEL_PREFIX + "%",),
    ).rowcount
    if n:
        log.append(f"[fix ] 清理就餐时间哨兵 {SENTINEL_PREFIX}*：{n} 行")

    # 2) target_size = 0（旧草稿默认值）改为 NULL，满足 CHECK 约束语义
    n = conn.execute("UPDATE teams SET target_size = NULL WHERE target_size = 0").rowcount
    if n:
        log.append(f"[fix ] 草稿 target_size=0 → NULL：{n} 行")

    # 3) 空字符串品类 → NULL
    n = conn.execute("UPDATE teams SET cuisine_type = NULL WHERE cuisine_type = ''").rowcount
    if n:
        log.append(f"[fix ] 空品类 → NULL：{n} 行")

    # 4) notifications.team_id 从 payload JSON 回填（幂等判定的结构化列）
    if _table_exists(conn, "notifications") and "team_id" in _cols(conn, "notifications"):
        rows = conn.execute(
            "SELECT id, payload FROM notifications WHERE team_id IS NULL"
        ).fetchall()
        filled = 0
        for rid, payload in rows:
            try:
                tid = json.loads(payload or "{}").get("team_id")
            except Exception:
                continue
            if isinstance(tid, int):
                conn.execute("UPDATE notifications SET team_id = ? WHERE id = ?", (tid, rid))
                filled += 1
        if filled:
            log.append(f"[fix ] notifications.team_id 回填：{filled} 行")

    # 5) checkin_code 唯一索引
    if _table_exists(conn, "checkins") and not _index_exists(conn, "uq_checkin_code"):
        try:
            conn.execute("CREATE UNIQUE INDEX uq_checkin_code ON checkins (checkin_code)")
            log.append("[idx ] uq_checkin_code（唯一）")
        except sqlite3.IntegrityError:
            log.append("[warn] checkins.checkin_code 存在重复值，未能建立唯一索引（请人工核查）")

    if _table_exists(conn, "notifications") and not _index_exists(
        conn, "ix_notifications_user_type_team"
    ):
        conn.execute(
            "CREATE INDEX ix_notifications_user_type_team "
            "ON notifications (user_id, type, team_id)"
        )
        log.append("[idx ] ix_notifications_user_type_team")

    if _table_exists(conn, "teams") and not _index_exists(conn, "ix_teams_status_dining"):
        conn.execute("CREATE INDEX ix_teams_status_dining ON teams (status, dining_time)")
        log.append("[idx ] ix_teams_status_dining")


def create_new_tables(engine, log: list[str]) -> None:
    """新表由 metadata 创建（只创建不存在的表）。"""
    from app import models  # noqa: F401
    from app.db import Base

    before = set(Base.metadata.tables)
    Base.metadata.create_all(engine)
    log.append(f"[tbl ] 确保 {len(before)} 张表存在（含新增表）")


def migrate(db_path: str) -> list[str]:
    log: list[str] = []
    if not os.path.exists(db_path):
        return [f"[warn] 数据库不存在：{db_path}"]

    from sqlalchemy import create_engine

    engine = create_engine(f"sqlite:///{db_path}")
    conn = engine.raw_connection()
    raw = conn.connection if hasattr(conn, "connection") else conn
    cur = raw.cursor()
    cur.execute("PRAGMA foreign_keys=OFF")
    cur.execute("PRAGMA legacy_alter_table=ON")

    add_columns(cur, "users", USER_COLUMNS, log)
    add_columns(cur, "notifications", NOTIFICATION_COLUMNS, log)
    add_columns(cur, "messages", MESSAGE_COLUMNS, log)

    # teams 需要在旧数据上重建：判据是"新结构标记是否齐全"，而不是简单的表存在与否
    # （否则每次执行都会白重建一次表）
    if _table_exists(cur, "teams"):
        cur_sql = cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='teams'"
        ).fetchone()[0] or ""
        has_new_cols = "fail_reason" in _cols(cur, "teams")
        has_checks = "ck_teams_no_oversell" in cur_sql
        nullable_dining = "dining_time DATETIME NOT NULL" not in cur_sql
        if not (has_new_cols and has_checks and nullable_dining):
            rebuild_teams(cur, engine, log)
        else:
            log.append("[skip] teams 结构已是目标版本")

    backfill(cur, log)
    cur.close()
    conn.commit()
    conn.close()

    create_new_tables(engine, log)
    engine.dispose()
    return log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--apply", action="store_true", help="应用到真实库（默认只在副本上演练）")
    args = ap.parse_args()

    if args.apply:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = os.path.join(BACKUP_DIR, f"{os.path.basename(args.db)}.pre-migrate-{stamp}")
        shutil.copy2(args.db, backup)
        print(f"[backup] {backup}")
        target = args.db
    else:
        tmp = tempfile.mkdtemp(prefix="dp-migrate-")
        target = os.path.join(tmp, "dryrun.db")
        shutil.copy2(args.db, target)
        print(f"[dry-run] 副本：{target}")

    log = migrate(target)
    for line in log:
        print(line)

    if not args.apply:
        print("\n[dry-run] 未改动真实库。确认无误后加 --apply 正式执行。")
    else:
        print("\n[ok] 迁移完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
