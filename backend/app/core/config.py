from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置（可用环境变量覆盖，前缀 DP_）"""

    model_config = ConfigDict(env_prefix="DP_", env_file=".env", extra="ignore")

    # 运行环境：dev 允许 mock 登录等便捷通道；prod 会强制校验危险默认值
    ENV: str = "dev"
    # 数据库
    DATABASE_URL: str = "sqlite:///./dining_plans.db"
    # JWT
    JWT_SECRET: str = "dining-plans-mvp-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 7
    # 支付宝登录（MVP 全走 mock）
    MOCK_ALIPAY: bool = True
    # 实名登记：mock=仅本地格式校验+摘要留痕（未接权威核验）；kyc=接入外部核验源
    REALNAME_MODE: str = "mock"
    # 证件号摘要的服务端 pepper（生产必须用环境变量覆盖；与 JWT_SECRET 同等敏感）
    ID_HASH_PEPPER: str = "dining-plans-mvp-pepper-change-me"
    # 业务时区偏移（小时）：全链路 naive 本地时间以此时区解释，出入站统一带偏移标记
    TIMEZONE_OFFSET_HOURS: int = 8
    # 同意协议版本：协议文本变更时必须递增，用于回溯用户同意的是哪一版
    CONSENT_VERSION: str = "1.0"
    # 后台 worker
    TASK_POLL_INTERVAL: float = 0.2
    REMINDER_INTERVAL_SECONDS: int = 300  # 核销超时提醒巡检周期
    CHECKIN_TIMEOUT_HOURS: int = 2  # 就餐时间之后多久算核销超时（进入提醒阶梯）
    # 核销截止：就餐时间 + N 小时后，未到场者视为缺席，按实际到场人数锁账（0=不启用宽限）
    CHECKIN_GRACE_HOURS: int = 2
    # 招募超时：就餐时间 + N 小时后仍未满员 → 自动 expired（0=不启用）
    RECRUITING_EXPIRE_GRACE_HOURS: int = 2
    # 通知阶梯（小时，相对就餐时间）：依次提醒队长 → 提醒全员 → 自动收口
    REMINDER_STAGE2_HOURS: int = 12
    REMINDER_STAGE3_HOURS: int = 24
    # 单用户被举报累计达到该值即自动限制（0=关闭自动限制，仅留工单）
    REPORT_AUTO_RESTRICT_THRESHOLD: int = 5
    # 订阅消息通道：none=只落库排队（未接正式 AppID 时的正确降级）；alipay=走支付宝订阅消息
    PUSH_PROVIDER: str = "none"
    # 限流（次/分钟），0=关闭
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH_PER_MIN: int = 20
    RATE_LIMIT_WRITE_PER_MIN: int = 60
    RATE_LIMIT_MESSAGE_PER_MIN: int = 20
    RATE_LIMIT_INVITE_TRY_PER_MIN: int = 10
    # CORS：逗号分隔白名单；"*" 表示放开（仅 dev 允许）
    CORS_ORIGINS: str = "*"
    # 群聊图片上传
    UPLOAD_DIR: str = "uploads"
    UPLOAD_MAX_BYTES: int = 2 * 1024 * 1024  # 单张 2MB
    UPLOAD_ALLOWED_TYPES: str = "image/jpeg,image/png,image/webp,image/gif"
    # 单用户每分钟最多上传张数
    UPLOAD_PER_MIN: int = 10

    def assert_production_ready(self) -> None:
        """生产环境 fail-fast：危险的开发默认值绝不允许带上去。"""
        if self.ENV != "prod":
            return
        problems = []
        if self.JWT_SECRET == "dining-plans-mvp-secret-change-me":
            problems.append("DP_JWT_SECRET 仍为默认值（可被用来伪造任意用户身份）")
        if self.ID_HASH_PEPPER == "dining-plans-mvp-pepper-change-me":
            problems.append("DP_ID_HASH_PEPPER 仍为默认值（证件号摘要可被反查）")
        if self.MOCK_ALIPAY:
            problems.append("DP_MOCK_ALIPAY=true（任意用户名可直接登录他人账号）")
        if self.CORS_ORIGINS.strip() == "*":
            problems.append("DP_CORS_ORIGINS=*（应收敛为白名单）")
        if problems:
            raise RuntimeError(
                "生产环境配置校验失败，已拒绝启动：\n  - " + "\n  - ".join(problems)
            )


settings = Settings()
