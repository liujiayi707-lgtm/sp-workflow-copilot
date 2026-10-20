
"""
SocialPeta Workflow Copilot
流程 B：客户群需求与 Bug 收集
第一版：模拟消息识别、分类和模板生成

暂不连接真实微信，不修改原始 Excel。
"""

import re
from typing import Any



BUG_KEYWORDS = [
    "bug", "报错", "错误", "异常", "无法使用",
    "用不了", "打不开", "下载不了", "无法下载",
    "没有反应", "没反应", "无响应", "无反应",
    "出问题", "有问题", "不对劲", "不对",
]


REQUEST_PATTERNS = [
    r"能不能.{0,30}",
    r"可不可以.{0,30}",
    r"希望.{0,30}",
    r"想要.{0,30}",
    r"需要增加.{0,30}",
    r"需要支持.{0,30}",
    r"增加.{0,30}功能",
    r"新增.{0,30}功能",
    r"建议.{0,30}",
    r"能否.{0,30}",
]

AMBIGUOUS_KEYWORDS = [
    "问题", "不对", "可以吗", "这样可以吗",
    "需要", "要", "想要", "能不能",
]

BUG_TEMPLATE = """【Bug 反馈信息收集】

1. 客户名称 / 账号：
2. 问题发生时间及涉及功能：
3. 实际发生的情况与预期结果：
4. 复现步骤及复现频率：
5. 错误提示、截图或录屏：
6. 影响范围及业务紧急程度：
7. 是否尝试过其他操作？问题是否仍然存在？
"""

REQUEST_TEMPLATE = """【新需求信息收集】

1. 客户名称 / 账号：
2. 需求标题及具体描述：
3. 当前业务场景与希望解决的问题：
4. 目前的操作方式及遇到的限制：
5. 期望实现的结果：
6. 影响范围及紧急程度：
7. 相关截图、示例或参考材料：
"""


def classify_message(message: str) -> dict[str, Any]:
    """
    根据规则初步识别消息类型。
    返回分类、是否建议发送模板、模板正文和识别原因。
    """

    text = message.strip()

    if not text:
        return {
            "category": "empty",
            "should_send_template": False,
            "template": None,
            "reason": "消息为空",
        }

    normalized = text.lower()

    # 明确的故障描述优先识别为 Bug。
    bug_match = any(
        keyword in normalized
        for keyword in BUG_KEYWORDS
    )

    if bug_match:
        return {
            "category": "bug",
            "should_send_template": True,
            "template": BUG_TEMPLATE,
            "reason": "命中明确的故障或异常关键词",
        }

    # 需要存在具体需求表达，才自动建议发送需求模板。
    request_match = any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in REQUEST_PATTERNS
    )

    if request_match:
        return {
            "category": "new_request",
            "should_send_template": True,
            "template": REQUEST_TEMPLATE,
            "reason": "命中明确的新需求表达",
        }

    # 模糊表达只标记待确认，不自动发送模板。
    ambiguous_match = any(
        keyword in normalized
        for keyword in AMBIGUOUS_KEYWORDS
    )

    if ambiguous_match:
        return {
            "category": "needs_confirmation",
            "should_send_template": False,
            "template": None,
            "reason": "存在潜在反馈信号，但信息不足，需要确认",
        }

    return {
        "category": "normal",
        "should_send_template": False,
        "template": None,
        "reason": "没有识别到明确的需求或 Bug 信号",
    }


def run_demo() -> None:
    """运行一组模拟客户群消息。"""

    test_messages = [
        ("A", "素材下载功能报错了，无法下载"),
        ("B", "能不能增加批量导出功能？"),
        ("C", "这个可以吗？"),
        ("A", "今天下午我们开会"),
        ("B", "需要增加一个筛选功能"),
        ("C", "这个结果不对"),
    ]

    for customer, message in test_messages:
        result = classify_message(message)

        print("=" * 55)
        print(f"模拟客户：{customer}")
        print(f"原始消息：{message}")
        print(f"分类结果：{result['category']}")
        print(f"建议发送模板：{result['should_send_template']}")
        print(f"识别原因：{result['reason']}")

        if result["template"]:
            print("\n模板预览：")
            print(result["template"])


if __name__ == "__main__":
    run_demo()

