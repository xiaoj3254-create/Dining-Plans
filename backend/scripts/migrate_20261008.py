"""2026-10-08 体验优化配套迁移。

新增结构：
- restaurants + latitude / longitude（广场「距离」标签、距离排序与半径筛选）
- messages    + mentions_all（仅队长可 @全体成员）

用法（默认 dry-run：只在库副本上跑并打印结论）：
    python scripts/migrate_20261008.py            # 副本演练
    python scripts/migrate_20261008.py --apply    # 应用到真实库（自动先备份）

幂等：可重复执行（列已存在则跳过，坐标按名称回填可重复执行）。
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
CATALOG = os.path.join(ROOT, "scripts", "menu_catalog.json")

RESTAURANT_COLUMNS = [("latitude", "NUMERIC(9,6)"), ("longitude", "NUMERIC(9,6)")]
MESSAGE_COLUMNS = [("mentions_all", "BOOLEAN NOT NULL DEFAULT 0")]


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def add_columns(conn: sqlite3.Connection, table: str, columns, log: list[str]) -> None:
    if not _table_exists(conn, table):
        log.append(f"[skip] {table} 不存在")
        return
    have = _cols(conn, table)
    for name, ddl in columns:
        if name in have:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        log.append(f"[add ] {table}.{name}")


def backfill_coords(conn: sqlite3.Connection, log: list[str]) -> None:
    """按餐馆名从单一数据源 menu_catalog.json 回填坐标（可重复执行）。"""
    if not _table_exists(conn, "restaurants") or "latitude" not in _cols(conn, "restaurants"):
        return
    if not os.path.exists(CATALOG):
        log.append("[warn] 未找到 menu_catalog.json，跳过坐标回填")
        return

    doc = json.load(open(CATALOG, encoding="utf-8"))
    by_name = {}
    for r in doc.get("restaurants", []):
        if r.get("latitude") is not None and r.get("longitude") is not None:
            by_name[r["name"]] = (r["latitude"], r["longitude"])

    filled = missed = 0
    for rid, name in conn.execute("SELECT id, name FROM restaurants").fetchall():
        point = by_name.get(name)
        if point is None:
            missed += 1
            continue
        cur = conn.execute(
            "UPDATE restaurants SET latitude=?, longitude=? WHERE id=? AND latitude IS NULL",
            (point[0], point[1], rid),
        )
        filled += cur.rowcount
    log.append(f"[fix ] 餐馆坐标回填：{filled} 行" + (f"（{missed} 家未在数据源中找到，保持为空）" if missed else ""))


def migrate(db_path: str) -> list[str]:
    log: list[str] = []
    if not os.path.exists(db_path):
        return [f"[warn] 数据库不存在：{db_path}"]

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=OFF")
    add_columns(conn, "restaurants", RESTAURANT_COLUMNS, log)
    add_columns(conn, "messages", MESSAGE_COLUMNS, log)
    backfill_coords(conn, log)
    conn.commit()
    conn.close()
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
        tmp = tempfile.mkdtemp(prefix="dp-migrate08-")
        target = os.path.join(tmp, "dryrun.db")
        shutil.copy2(args.db, target)
        print(f"[dry-run] 副本：{target}")

    for line in migrate(target):
        print(line)

    print("\n[ok] 迁移完成。" if args.apply else "\n[dry-run] 未改动真实库。确认无误后加 --apply 正式执行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
