
import sp_workflow.systems.database as database

from sp_workflow.skills.feedback_processor import process_message


def prepare_test_db(monkeypatch, tmp_path):
    """每个测试使用独立数据库，不污染演示数据。"""
    monkeypatch.setattr(
        database,
        "DB_PATH",
        tmp_path / "test_feedback.db",
    )
    database.init_db()


def test_new_bug_creates_feedback(monkeypatch, tmp_path):
    prepare_test_db(monkeypatch, tmp_path)

    result = process_message(
        customer_code="TEST_A",
        message_text="素材下载功能报错，无法下载",
    )

    assert result["action"] == "created"
    assert result["category"] == "bug"
    assert result["feedback_id"] is not None

    records = database.get_feedbacks("TEST_A")
    assert len(records) == 1


def test_followup_appends_to_same_feedback(monkeypatch, tmp_path):
    prepare_test_db(monkeypatch, tmp_path)

    first = process_message(
        customer_code="TEST_B",
        message_text="素材下载功能报错，无法下载",
    )

    second = process_message(
        customer_code="TEST_B",
        message_text="今天上午开始出现问题，重试后仍无法下载",
        feedback_id=first["feedback_id"],
    )

    assert second["action"] == "appended"
    assert second["feedback_id"] == first["feedback_id"]

    records = database.get_feedbacks("TEST_B")
    assert len(records) == 1
    assert "素材下载功能报错" in records[0]["description"]
    assert "今天上午开始出现问题" in records[0]["description"]


def test_normal_message_does_not_create_feedback(
    monkeypatch, tmp_path
):
    prepare_test_db(monkeypatch, tmp_path)

    result = process_message(
        customer_code="TEST_C",
        message_text="今天下午我们开会",
    )

    assert result["action"] == "ignored"
    assert result["feedback_id"] is None
    assert database.get_feedbacks("TEST_C") == []

    messages = database.get_messages("TEST_C")
    assert len(messages) == 1


def test_duplicate_followup_is_not_appended(
    monkeypatch, tmp_path
):
    prepare_test_db(monkeypatch, tmp_path)

    first = process_message(
        customer_code="TEST_D",
        message_text="素材下载功能报错，无法下载",
    )

    original = database.get_feedbacks("TEST_D")[0]["description"]

    second = process_message(
        customer_code="TEST_D",
        message_text="素材下载功能报错，无法下载",
        feedback_id=first["feedback_id"],
    )

    assert second["action"] == "not_appended"

    records = database.get_feedbacks("TEST_D")
    assert len(records) == 1
    assert records[0]["description"] == original

def test_followup_automatically_matches_single_feedback(
    monkeypatch, tmp_path
):
    prepare_test_db(monkeypatch, tmp_path)

    first = process_message(
        customer_code="TEST_AUTO",
        message_text="素材下载功能报错，无法下载",
    )

    second = process_message(
        customer_code="TEST_AUTO",
        message_text="今天上午开始出现问题，重试后仍无法下载",
    )

    assert first["action"] == "created"
    assert second["action"] == "appended"
    assert second["feedback_id"] == first["feedback_id"]

    records = database.get_feedbacks("TEST_AUTO")
    assert len(records) == 1
    assert "重试后仍无法下载" in records[0]["description"]


def test_ambiguous_followup_requires_confirmation(
    monkeypatch, tmp_path
):
    prepare_test_db(monkeypatch, tmp_path)

    process_message(
        customer_code="TEST_MULTI",
        message_text="素材下载功能报错，无法下载",
    )

    process_message(
        customer_code="TEST_MULTI",
        message_text="能不能增加批量导出功能？",
    )

    result = process_message(
        customer_code="TEST_MULTI",
        message_text="刚才那个还是不行",
    )

    assert result["action"] == "needs_confirmation"
    assert result["feedback_id"] is None

    # 两条原始反馈都应保留，不应被错误合并。
    records = database.get_feedbacks("TEST_MULTI")
    assert len(records) == 2

def test_saved_message_links_to_feedback(monkeypatch, tmp_path):
    prepare_test_db(monkeypatch, tmp_path)

    first = process_message(
        customer_code="TEST_LINK",
        message_text="素材下载功能报错，无法下载",
    )

    second = process_message(
        customer_code="TEST_LINK",
        message_text="补充一下，今天上午开始出现问题",
        feedback_id=first["feedback_id"],
    )

    assert second["action"] == "appended"

    messages = database.get_messages("TEST_LINK")
    linked_message = next(
        item for item in messages
        if item["id"] == second["message_id"]
    )

    assert linked_message["feedback_id"] == first["feedback_id"]


def test_feedback_cannot_be_updated_by_another_customer(
    monkeypatch, tmp_path
):
    prepare_test_db(monkeypatch, tmp_path)

    first = process_message(
        customer_code="TEST_OWNER",
        message_text="素材下载功能报错，无法下载",
    )

    result = process_message(
        customer_code="TEST_OTHER",
        message_text="补充一下，仍然无法下载",
        feedback_id=first["feedback_id"],
    )

    assert result["action"] == "needs_confirmation"
    assert result["feedback_id"] is None

    owner_records = database.get_feedbacks("TEST_OWNER")
    other_records = database.get_feedbacks("TEST_OTHER")

    assert len(owner_records) == 1
    assert len(other_records) == 0
    assert "仍然无法下载" not in owner_records[0]["description"]
