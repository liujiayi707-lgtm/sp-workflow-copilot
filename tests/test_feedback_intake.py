
from sp_workflow.skills.feedback_intake import classify_message
from sp_workflow.systems.database import (
    init_db,
    save_message,
    get_messages,
)


def test_bug_message_classification():
    result = classify_message("素材下载功能报错了，无法下载")
    assert result["category"] == "bug"
    assert result["should_send_template"] is True


def test_request_message_classification():
    result = classify_message("能不能增加批量导出功能？")
    assert result["category"] == "new_request"
    assert result["should_send_template"] is True


def test_ambiguous_message_classification():
    result = classify_message("这个可以吗？")
    assert result["category"] == "needs_confirmation"
    assert result["should_send_template"] is False


def test_message_can_be_saved_and_read():
    init_db()

    message = "自动化测试消息：下载报错"
    message_id = save_message(
        customer_code="TEST_CUSTOMER",
        group_code="TEST_GROUP",
        sender="自动化测试",
        message_text=message,
        category="bug",
        should_send_template=True,
    )

    assert message_id > 0

    records = get_messages("TEST_CUSTOMER")
    assert any(
        row["message_text"] == message
        for row in records
    )
def test_append_feedback_information():
    from sp_workflow.systems.database import (
        init_db,
        create_feedback,
        append_feedback_information,
        get_feedbacks,
    )

    init_db()

    feedback_id = create_feedback(
        customer_code="TEST_APPEND",
        category="bug",
        title="测试反馈追加",
        description="素材下载功能报错",
        urgency="待确认",
    )

    # 第一次追加应成功
    assert append_feedback_information(
        feedback_id,
        "今天上午开始出现问题",
    ) is True

    # 相同内容不应重复追加
    assert append_feedback_information(
        feedback_id,
        "今天上午开始出现问题",
    ) is False

    records = get_feedbacks("TEST_APPEND")
    record = next(
        item for item in records
        if item["id"] == feedback_id
    )

    assert "素材下载功能报错" in record["description"]
    assert "今天上午开始出现问题" in record["description"]


def test_append_to_nonexistent_feedback():
    from sp_workflow.systems.database import (
        init_db,
        append_feedback_information,
    )

    init_db()

    assert append_feedback_information(
        999999999,
        "这条反馈不存在",
    ) is False
