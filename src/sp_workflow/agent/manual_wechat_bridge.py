
"""
SP Workflow Copilot
流程 B：个人微信群人工消息桥接入口

工作方式：
1. 人工复制微信群消息并输入本程序。
2. 调用已有 feedback_processor 处理消息。
3. 展示分类结果、反馈编号和建议模板。
4. 人工审核后，自行复制模板发送回微信群。

不自动读取微信，不自动发送微信消息。
"""

from sp_workflow.skills.feedback_processor import process_message


CUSTOMERS = {
    "A": {
        "customer_code": "CUSTOMER_A",
        "group_code": "WECHAT_TEST_GROUP_A",
    },
    "B": {
        "customer_code": "CUSTOMER_B",
        "group_code": "WECHAT_TEST_GROUP_B",
    },
    "C": {
        "customer_code": "CUSTOMER_C",
        "group_code": "WECHAT_TEST_GROUP_C",
    },
}


def print_result(result: dict) -> None:
    """展示消息处理结果。"""

    print("\n" + "=" * 55)
    print("处理结果")
    print("=" * 55)

    print(f"消息 ID：{result['message_id']}")
    print(f"客户代码：{result['customer_code']}")
    print(f"消息分类：{result['category']}")
    print(f"处理动作：{result['action']}")
    print(f"反馈 ID：{result['feedback_id']}")
    print(f"识别原因：{result['reason']}")

    if result["should_send_template"] and result["template"]:
        print("\n建议发送的收集模板：")
        print("-" * 55)
        print(result["template"])
        print("-" * 55)
        print("请人工检查后，再决定是否发送到微信群。")

    if result["action"] == "needs_confirmation":
        print("\n需要人工确认关联目标，不要直接创建或合并工单。")

    if result["action"] == "not_appended":
        print("\n本次没有追加新内容，可能是重复内容或没有成功更新。")


def main() -> None:
    """运行可控的人工消息桥接程序。"""

    print("=" * 55)
    print("SP Workflow Copilot | 微信群人工消息桥接")
    print("=" * 55)
    print("当前版本不会自动读取或发送微信消息。")
    print("输入 ON 启动人工消息处理，OFF 暂停，STATUS 查看状态，Q 退出。")

    bridge_enabled = False

    while True:
        print("\n" + "-" * 55)
        print(
            f"当前状态：{'运行中' if bridge_enabled else '已暂停'}"
        )

        command = input(
            "请输入命令（ON / OFF / STATUS / Q）："
        ).strip().upper()

        if command == "Q":
            print("程序已退出。")
            break

        if command == "ON":
            bridge_enabled = True
            print("人工消息处理已启动。")
            continue

        if command == "OFF":
            bridge_enabled = False
            print("人工消息处理已暂停。")
            continue

        if command == "STATUS":
            print(
                "当前状态："
                + ("运行中" if bridge_enabled else "已暂停")
            )
            continue

        if not bridge_enabled:
            print("程序目前已暂停，请先输入 ON。")
            continue

        if command not in CUSTOMERS:
            print("无效输入，请输入 ON、OFF、STATUS、Q 或 A/B/C。")
            continue

        customer = CUSTOMERS[command]

        sender = input(
            "请输入发送者标识（建议使用脱敏名称）："
        ).strip()

        message_text = input(
            "请粘贴一条微信群消息：\n"
        ).strip()

        if message_text.upper() == "Q":
            print("程序已退出。")
            break

        if not message_text:
            print("消息不能为空，本次不处理。")
            continue

        feedback_input = input(
            "如果明确知道要补充哪条反馈，请输入反馈 ID；"
            "否则直接回车："
        ).strip()

        feedback_id = None

        if feedback_input:
            try:
                feedback_id = int(feedback_input)
                if feedback_id <= 0:
                    raise ValueError
            except ValueError:
                print("反馈 ID 必须是正整数，本条消息不处理。")
                continue

        try:
            result = process_message(
                customer_code=customer["customer_code"],
                group_code=customer["group_code"],
                sender=sender,
                message_text=message_text,
                feedback_id=feedback_id,
            )
            print_result(result)

        except Exception as exc:
            print(f"\n处理失败：{type(exc).__name__}: {exc}")
            print("请保留错误信息，不要重复提交同一条消息。")


if __name__ == "__main__":
    main()


