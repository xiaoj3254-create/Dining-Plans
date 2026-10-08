"""原子名额操作（SQLite 场景并发安全核心）。

原理：SQLite 单写者。条件 UPDATE 在 BEGIN-级写锁内串行执行：
  UPDATE teams SET current_size = current_size + 1, version = version + 1
  WHERE id=:tid AND status='recruiting' AND current_size < target_size
rowcount==1 即抢到名额；两个并发 JOIN 必然一胜一败，绝不超卖。
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def try_increment_size(db: Session, team_id: int) -> bool:
    """原子抢占一个名额。成功 True；满员/已关闭/不存在返回 False"""
    res = db.execute(
        text(
            """
            UPDATE teams
            SET current_size = current_size + 1, version = version + 1
            WHERE id = :tid AND status = 'recruiting' AND current_size < target_size
            """
        ),
        {"tid": team_id},
    )
    return res.rowcount == 1


def decrement_size(db: Session, team_id: int) -> None:
    db.execute(
        text("UPDATE teams SET current_size = current_size - 1 WHERE id = :tid AND current_size > 0"),
        {"tid": team_id},
    )


def try_increment_size_for_formed(db: Session, team_id: int) -> bool:
    """成团后补招专用的原子占位。

    与报名的区别：允许在 formed 状态下占用空余名额（成团后退队释放的位子）；
    仍受 `current_size < target_size` 与 DB CHECK 双重约束，绝不超卖。
    """
    res = db.execute(
        text(
            """
            UPDATE teams
            SET current_size = current_size + 1, version = version + 1
            WHERE id = :tid AND status = 'formed' AND current_size < target_size
            """
        ),
        {"tid": team_id},
    )
    return res.rowcount == 1
