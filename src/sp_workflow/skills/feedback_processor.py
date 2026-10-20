
"""
流程 B：客户群反馈处理器
第一阶段：模拟消息分类、反馈创建、后续信息匹配。
不连接真实微信，不修改原始 Excel。
"""

from sp_workflow.skills.feedback_intake import classify_message
from sp_workflow.systems.database import (
    init_db,
    save_message,
    create_feedback,
    get_feedbacks,
    append_feedback_information,
)


# 只有较明确的后续表达才触发自动匹配。
FOLLOWUP_CUES = (
    "刚才那个",
    "刚才说的",
    "上面那个",
    "这个问题",
    "这个bug",
    "这个 bug",
    "还是不行",
    "仍然",
    "仍无法",
    "依旧",
    "重试后",
    "再次出现",
    "补充一下",
    "补充信息",
)


def is_followup_message(message: str) -> bool:
    """判断消息是否包含明显的后续补充表达。"""
    text = message.strip().lower()
    return any(cue in text for cue in FOLLOWUP_CUES)


def process_message(
    customer_code: str,
    message_text: str,
    group_code: str = "",
    sender: str = "",
    feedback_id: int | None = None,
) -> dict:
    """分类、匹配或创建反馈，并保存原始消息。"""

    init_db()

    result = classify_message(message_text)
    category = result["category"]
    linked_feedback_id = None
    action = "ignored"
    reason = result["reason"]

    # 只允许关联同一客户尚在收集中的反馈。
    customer_feedbacks = get_feedbacks(customer_code)
    open_feedbacks = [
        item for item in customer_feedbacks
        if item["status"] == "collecting"
    ]

    # 情况一：调用方已经明确指定反馈 ID。
    if feedback_id is not None:
        target = next(
            (
                item for item in open_feedbacks
                if item["id"] == feedback_id
            ),
            None,
        )

        if target is None:
            action = "needs_confirmation"
            category = "needs_confirmation"
            reason = "指定的反馈不存在、不属于该客户或已不在收集状态"

        elif (
            category in {"bug", "new_request", "needs_confirmation"}
            or is_followup_message(message_text)
        ):
            linked_feedback_id = feedback_id

            appended = append_feedback_information(
                feedback_id,
                message_text,
            )

            action = "appended" if appended else "not_appended"

        else:
            action = "ignored"

    # 情况二：没有指定 ID，尝试自动匹配后续消息。
    elif is_followup_message(message_text):
        if len(open_feedbacks) == 1:
            target = open_feedbacks[0]
            linked_feedback_id = target["id"]

            appended = append_feedback_information(
                target["id"],
                message_text,
            )

            action = "appended" if appended else "not_appended"
            reason = "找到该客户唯一一条待收集反馈，尝试追加后续信息"

        elif len(open_feedbacks) > 1:
            action = "needs_confirmation"
            category = "needs_confirmation"
            reason = "该客户存在多条待收集反馈，无法安全确定关联目标"

        else:
            action = "needs_confirmation"
            category = "needs_confirmation"
            reason = "识别到后续表达，但没有可匹配的待收集反馈"

    # 情况三：没有匹配到后续反馈，按分类处理新消息。
    elif category in {"bug", "new_request"}:
        linked_feedback_id = create_feedback(
            customer_code=customer_code,
            category=category,
            title=message_text[:80],
            description=message_text,
            urgency="待确认",
        )
        action = "created"

    elif category == "needs_confirmation":
        action = "needs_confirmation"

    # 保存消息，并记录成功关联的反馈 ID。
    message_id = save_message(
        customer_code=customer_code,
        group_code=group_code,
        sender=sender,
        message_text=message_text,
        category=category,
        should_send_template=(
            result["should_send_template"]
            if action != "needs_confirmation"
            else False
        ),
        feedback_id=linked_feedback_id,
    )

    return {
        "message_id": message_id,
        "customer_code": customer_code,
        "category": category,
        "action": action,
        "feedback_id": linked_feedback_id,
        "should_send_template": (
            result["should_send_template"]
            if action != "needs_confirmation"
            else False
        ),
        "template": (
            result["template"]
            if action != "needs_confirmation"
            else None
        ),
        "reason": reason,
    }


def run_demo() -> None:
    """演示创建反馈并自动匹配后续补充。"""

    first = process_message(
        customer_code="DEMO_AUTO",
        group_code="DEMO_GROUP_AUTO",
        sender="模拟客户",
        message_text="素材下载功能报错，无法下载",
    )

    print("第一次处理：")
    print(first)

    second = process_message(
        customer_code="DEMO_AUTO",
        group_code="DEMO_GROUP_AUTO",
        sender="模拟客户",
        message_text="今天上午开始出现问题，重试后仍无法下载",
    )

    print("\n第二次处理：")
    print(second)

    print("\n客户反馈记录：")
    for item in get_feedbacks("DEMO_AUTO"):
        print(item)


if __name__ == "__main__":
    run_demo()
