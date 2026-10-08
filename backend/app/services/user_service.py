"""用户服务：资料维护、实名登记、同意留痕、注销。

实名相关修复（原实现"提交即通过"）：
1. 姓名与证件号做真实格式校验（含 18 位身份证 GB 11643 校验位）；
2. 从证件号解析出生日期，与用户自填年龄交叉校验 → 堵住"改年龄绕过 18 岁门槛"；
3. 实名后禁止再修改年龄；
4. 敏感信息需**单独同意**并落库版本号（PIPL）；
5. 证件摘要改用 HMAC + pepper，不再是可反查的裸 SHA256。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.states import MemberStatus, TeamStatus
from app.core.audit import audit
from app.core.config import settings
from app.core.idcard import (
    MIN_AGE,
    age_of,
    birth_date_str,
    parse_birth_date_str,
    validate_id_card,
    validate_real_name,
)
from app.core.security import hash_sensitive
from app.core.timeutil import now
from app.models.member import TeamMember
from app.models.team import Team
from app.models.user import User
from app.schemas.serializers import (
    bill_status_of,
    iso,
    recruit_deadline,
    restaurant_summary,
)


def update_profile(db: Session, user: User, data) -> User:
    if data.nickname is not None:
        user.nickname = data.nickname.strip()
    if data.age is not None:
        # 实名后年龄与证件绑定，不允许再改（否则 18 岁门槛可被绕过）
        if user.real_name_verified and data.age != user.age:
            from fastapi import HTTPException

            raise HTTPException(status_code=409, detail="年龄已与实名信息绑定，不可修改")
        if data.age < MIN_AGE:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail=f"仅限 {MIN_AGE} 周岁以上用户使用线下拼桌功能")
        user.age = data.age
    if data.gender is not None:
        user.gender = data.gender
    db.commit()
    return user


def record_consent(db: Session, user: User, version: str) -> User:
    """记录用户同意的协议版本（首启同意门 / 注册时同意）。"""
    user.consent_version = version[:20]
    user.consent_at = now()
    audit(db, user.id, "consent.accept", "user", user.id, version=version)
    db.commit()
    return user


def submit_realname(db: Session, user: User, data) -> User:
    """实名登记：格式校验 + 年龄交叉校验 + 单独同意留痕 + 带盐摘要。

    注意：`settings.REALNAME_MODE == "mock"` 时仅做**本地格式校验**，
    不等价于公安/运营商权威核验；产品文案必须如实说明（见前端"实名登记"说明）。
    """
    from fastapi import HTTPException

    if not data.consent:
        raise HTTPException(
            status_code=422,
            detail="请先阅读并同意《实名登记与个人信息处理规则》后再提交",
        )

    ok, msg = validate_real_name(data.real_name)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)

    ok, msg, birth = validate_id_card(data.id_card)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)

    derived_age = age_of(birth)
    if derived_age < MIN_AGE:
        raise HTTPException(
            status_code=422,
            detail=f"证件出生日期显示未满 {MIN_AGE} 周岁，暂不可使用线下拼桌功能",
        )

    user.real_name_verified = True
    user.real_name_hash = hash_sensitive(data.real_name)
    user.id_card_hash = hash_sensitive(data.id_card)
    user.birth_date = birth_date_str(birth)
    # 年龄以证件为准：用户自填年龄一律被证件推算值覆盖，
    # 从根上杜绝"填 18 岁、实际未成年"或"实名后再改年龄"绕过年龄门槛
    user.age = derived_age
    user.realname_consent_at = now()
    user.consent_version = settings.CONSENT_VERSION
    if user.consent_at is None:
        user.consent_at = now()
    audit(db, user.id, "user.realname", "user", user.id, mode=settings.REALNAME_MODE)
    db.commit()
    return user


def delete_account(db: Session, user: User) -> dict:
    """注销账号：匿名化个人信息 + 立即失效全部 token，保留队伍结构。

    PIPL 第 47 条要求的删除权。历史成员记录不物理删除是为了不破坏已成团队伍的
    账目与核销记录（其他成员的合法权益），只把个人信息替换为匿名占位。
    """
    if user.deleted_at is not None:
        return {"deleted": True, "already": True}

    # 仍在进行中的队伍需要收口，避免队长消失导致他人被卡住
    leader_teams = db.execute(
        select(Team).where(
            Team.leader_id == user.id,
            Team.status.in_([TeamStatus.DRAFT.value, TeamStatus.RECRUITING.value]),
        )
    ).scalars().all()
    for team in leader_teams:
        team.status = TeamStatus.FAILED.value
        team.failed_at = now()
        team.fail_reason = "user_deleted"

    user.nickname = f"已注销用户{user.id}"
    user.real_name_hash = None
    user.id_card_hash = None
    user.birth_date = None
    user.alipay_user_id = None
    user.password_hash = None
    user.real_name_verified = False
    user.deleted_at = now()
    user.token_version = (user.token_version or 0) + 1  # 旧 token 立即失效
    audit(db, user.id, "user.delete", "user", user.id, closed_teams=len(leader_teams))
    db.commit()
    return {"deleted": True, "closed_teams": len(leader_teams)}


def realname_age_consistent(user: User) -> bool:
    """实名信息与年龄是否仍然自洽（巡检/风控用）。"""
    birth = parse_birth_date_str(user.birth_date)
    if birth is None:
        return True
    return abs(age_of(birth) - user.age) <= 1


def my_teams(db: Session, user: User) -> dict:
    rows = (
        db.execute(
            select(TeamMember, Team)
            .join(Team, Team.id == TeamMember.team_id)
            .where(TeamMember.user_id == user.id, TeamMember.status == MemberStatus.ACTIVE)
            .order_by(Team.created_at.desc())
        )
        .all()
    )
    groups: dict[str, list] = {"draft": [], "recruiting": [], "formed": [], "completed": [], "failed": []}
    for member, team in rows:
        # 注销/注销队伍也要能在列表里看到终态，避免"我的组队"里凭空消失
        groups.setdefault(team.status, []).append(
            {
                "id": team.id,
                "name": team.name,
                "mode": team.mode,
                "status": team.status,
                "cuisine_type": team.cuisine_type,
                "dining_time": iso(team.dining_time),
                "current_size": team.current_size,
                "target_size": team.target_size,
                "remaining": (
                    team.target_size - team.current_size if team.target_size is not None else None
                ),
                "my_role": member.role,
                "fail_reason": team.fail_reason,
                # 邀请码只发给该队成员：供「我的组队」里的快捷分享携带
                "code": team.code if team.mode == "invite" else None,
                # 餐馆摘要（含坐标）供列表卡片展示店名与客户端算距离
                "restaurant": restaurant_summary(db, team),
                "bill_status": bill_status_of(db, team),
                "recruit_deadline": iso(recruit_deadline(team)),
            }
        )
    return {"groups": groups}
