import hashlib
import hmac
import os
import time
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings


# ---------- 密码（PBKDF2，免 bcrypt 依赖） ----------

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    iterations = 100_000
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        # 常数时间比较，防时序侧信道
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def hash_sensitive(text: str) -> str:
    """证件号等敏感标识的摘要：HMAC-SHA256 + 服务端 pepper。

    为什么不用裸 SHA256：身份证号取值空间远小于口令（地区码+出生日期+顺序码+校验位
    实际可枚举），裸摘要拿到库就能大规模反查。加 pepper 后必须同时掌握密钥才能枚举，
    且保持确定性（可用作"同一证件号重复注册"的判重依据）。
    """
    normalized = (text or "").strip().upper().encode()
    return hmac.new(
        settings.ID_HASH_PEPPER.encode(), normalized, hashlib.sha256
    ).hexdigest()


# ---------- JWT ----------

def create_token(user_id: int, token_version: int = 0) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "ver": token_version,  # 注销 / 强制下线时递增，使旧 token 立即失效
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.JWT_EXPIRE_DAYS)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    """解析 JWT，成功返回 payload（含 sub/ver），失败返回 None"""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except Exception:
        return None


def decode_user_id(token: str) -> int | None:
    payload = decode_token(token)
    if not payload:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
