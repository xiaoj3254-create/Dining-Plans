"""群聊/文案内容安全检查（本地词表，可外接内容安全服务）。

审计发现：群聊是陌生人成团后的主要沟通渠道，原实现把 500 字任意文本
原样入库并广播，无任何过滤。线下见面的前期沟通恰恰是风险最高的一段。

设计：`check_text()` 返回命中结果；命中即拒绝发送并记录审计。
词表可通过环境变量/文件扩展，也可在 `providers/` 下替换为云内容安全 SDK。
"""

import re
import unicodedata

# 分类词表（MVP 内置最小集；生产应替换为云内容安全服务 + 运营可维护词库）
BUILTIN_WORDS: dict[str, tuple[str, ...]] = {
    # 违法交易 / 涉黄涉赌毒
    "illegal": (
        "毒品", "冰毒", "大麻", "枪支", "买枪", "赌博", "博彩", "开盘口",
        "嫖", "援交", "包养", "招嫖", "开房服务",
    ),
    # 诈骗引流：诱导转账、代付、刷单
    "fraud": (
        "刷单", "返利", "刷流水", "代付", "扫码转账", "先转账", "保证金",
        "解冻费", "稳赚", "内幕消息", "带你赚钱",
    ),
    # 人身威胁 / 骚扰
    "abuse": (
        "弄死你", "打死你", "定位你", "上门堵你", "人肉你",
    ),
}

# 归一化时剔除的装饰性字符（防止 "毒 品" / "毒*品" 之类简单绕过）
_STRIP_RE = re.compile(r"[\s\-_*·.,，。！!?？~～|/\\()（）\[\]【】]+")


class TextRejected(Exception):
    """内容命中安全策略"""

    def __init__(self, category: str, message: str):
        self.category = category
        self.message = message
        super().__init__(message)


def normalize(text: str) -> str:
    """全角转半角 + 去除装饰字符 + 转小写，供匹配使用（不改动原文入库）。"""
    folded = unicodedata.normalize("NFKC", text or "")
    return _STRIP_RE.sub("", folded).lower()


def find_hit(text: str) -> tuple[str, str] | None:
    """返回 (category, 命中的词) 或 None。"""
    if not text:
        return None
    norm = normalize(text)
    for category, words in BUILTIN_WORDS.items():
        for word in words:
            if normalize(word) in norm:
                return category, word
    return None


CATEGORY_LABELS = {
    "illegal": "疑似违法信息",
    "fraud": "疑似诈骗引流",
    "abuse": "疑似人身威胁或骚扰",
}


def check_text(text: str) -> None:
    """校验文本，命中策略时抛 TextRejected。"""
    hit = find_hit(text)
    if hit is None:
        return
    category, word = hit
    label = CATEGORY_LABELS.get(category, "违规内容")
    raise TextRejected(category, f"{label}，已阻止发送（命中：{word}）")
