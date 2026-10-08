"""身份证号 / 姓名格式校验（本地规则校验，不替代权威核验源）。

审计发现：原实现只校验长度，`real_name="ab"` + `id_card="123456"` 即可通过
"实名认证"，而前端对外宣称"实名核验"——属于对用户的不实安全承诺。

本模块做两件事：
1. 把格式门槛提到"至少是合法身份证号"（含 GB 11643 校验位）；
2. **从证件号解析出生日期**，用于交叉校验用户自填年龄，堵住
   "实名后随便改年龄"绕过年龄门槛的路径。
"""

import re
from datetime import date, datetime

# GB 11643-1999 18 位身份证：加权因子与校验码映射
_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_CHECK_CODES = "10X98765432"

_ID18_RE = re.compile(r"^\d{17}[\dXx]$")
# 姓名：2-30 个汉字，允许少数民族分隔号 ·（如"阿依古丽·买买提"）；
# 首尾必须是汉字，纯拉丁/数字一律拒绝（"ab" 这类占位名不能通过实名登记）
_NAME_RE = re.compile(r"^[\u4e00-\u9fa5][\u4e00-\u9fa5·]{0,28}[\u4e00-\u9fa5]$")

MIN_AGE = 18


def validate_real_name(name: str) -> tuple[bool, str]:
    """姓名格式校验。返回 (ok, 中文错误信息)"""
    value = (name or "").strip()
    if not value:
        return False, "请填写真实姓名"
    if not _NAME_RE.match(value):
        return False, "姓名格式不正确（需为 2-30 位汉字，可含 · 分隔号）"
    return True, ""


def parse_birth_date(id_card: str) -> date | None:
    """从 18 位身份证号解析出生日期；非法返回 None。"""
    value = (id_card or "").strip().upper()
    if not _ID18_RE.match(value):
        return None
    try:
        year = int(value[6:10])
        month = int(value[10:12])
        day = int(value[12:14])
        return date(year, month, day)
    except ValueError:
        return None


def validate_id_card(id_card: str) -> tuple[bool, str, date | None]:
    """身份证号校验（格式 + 出生日期合法性 + GB 11643 校验位）。

    返回 (ok, 中文错误信息, 出生日期)
    """
    value = (id_card or "").strip().upper()
    if not value:
        return False, "请填写证件号码", None
    if not _ID18_RE.match(value):
        return False, "证件号格式不正确（需为 18 位居民身份证号）", None

    birth = parse_birth_date(value)
    if birth is None:
        return False, "证件号中的出生日期不合法", None
    if birth > date.today():
        return False, "证件号中的出生日期晚于今天", None

    total = sum(int(value[i]) * _WEIGHTS[i] for i in range(17))
    if _CHECK_CODES[total % 11] != value[17]:
        return False, "证件号校验位不正确，请核对后重填", None

    return True, "", birth


def age_of(birth: date, on: date | None = None) -> int:
    """按周岁计算年龄。"""
    ref = on or date.today()
    years = ref.year - birth.year
    if (ref.month, ref.day) < (birth.month, birth.day):
        years -= 1
    return years


def birth_date_str(birth: date) -> str:
    return birth.strftime("%Y-%m-%d")


def parse_birth_date_str(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
