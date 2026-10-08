"""文件上传（MVP：仅群聊图片）。

安全要求（陌生人社交场景下"发图"是最容易被滥用的入口）：
- 白名单 MIME + 扩展名，不接受 svg（可执行脚本）等；
- 大小上限（`DP_UPLOAD_MAX_BYTES`，默认 2MB）；
- **文件名完全由服务端随机生成**，绝不使用客户端文件名，避免路径穿越与覆盖；
- 只落盘到 `uploads/chat/`，由 StaticFiles 以只读方式托管；
- 每用户每分钟上传次数限流。
"""

import re
import secrets
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import settings

# MIME → 落地扩展名（白名单，写死映射，不信任客户端提供的文件名/后缀）
ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

_SAFE_NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp|gif)$")

# 对外 URL 前缀（与 main.py 的 StaticFiles 挂载点保持一致）
URL_PREFIX = "/uploads"


def allowed_mime() -> set[str]:
    return {t.strip().lower() for t in settings.UPLOAD_ALLOWED_TYPES.split(",") if t.strip()}


def upload_root() -> Path:
    # 相对路径基于 backend/ 运行目录解析
    root = Path(settings.UPLOAD_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_image(file: UploadFile, subdir: str = "chat") -> dict:
    """保存图片，返回 {url, size, content_type}。URL 为站点相对路径。"""
    mime = (file.content_type or "").lower().split(";")[0].strip()
    if mime not in allowed_mime() or mime not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=422,
            detail="仅支持 jpg / png / webp / gif 格式的图片",
        )

    data = file.file.read()
    if not data:
        raise HTTPException(status_code=422, detail="图片内容为空")
    if len(data) > settings.UPLOAD_MAX_BYTES:
        limit_mb = settings.UPLOAD_MAX_BYTES / 1024 / 1024
        raise HTTPException(status_code=413, detail=f"图片过大，请压缩到 {limit_mb:.0f}MB 以内")

    # 简单魔数校验：防止把非图片内容伪装成 image/* 上传
    if not _looks_like_image(data):
        raise HTTPException(status_code=422, detail="文件内容不像有效图片，已拒绝")

    name = f"{secrets.token_hex(16)}{ALLOWED_TYPES[mime]}"
    if not _SAFE_NAME.match(name):  # 自我校验：绝不可能产生非法文件名
        raise HTTPException(status_code=500, detail="文件名生成异常")

    target_dir = upload_root() / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / name).write_bytes(data)

    return {
        # URL 固定挂在 /uploads 挂载点下，与磁盘目录（DP_UPLOAD_DIR，可为绝对路径）
        # 解耦——把绝对路径拼进 URL 会在测试/换目录时直接泄漏文件系统结构
        "url": f"{URL_PREFIX}/{subdir}/{name}",
        "size": len(data),
        "content_type": mime,
    }


def _looks_like_image(data: bytes) -> bool:
    if data.startswith(b"\xff\xd8\xff"):          # JPEG
        return True
    if data.startswith(b"\x89PNG\r\n\x1a\n"):     # PNG
        return True
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return False


def is_own_upload_url(url: str) -> bool:
    """图片消息的 content 必须是我们自己托管的路径，禁止外链（防盗图/防钓鱼）。"""
    if not url or not isinstance(url, str):
        return False
    prefix = f"{URL_PREFIX}/chat/"
    if not url.startswith(prefix):
        return False
    return bool(_SAFE_NAME.match(url[len(prefix):]))
