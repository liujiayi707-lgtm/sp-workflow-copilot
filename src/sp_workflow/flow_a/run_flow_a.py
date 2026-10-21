"""Run the Flow A customer-success workflow locally."""

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "artifacts" / "flow_a"
FEEDBACK_CSV = ARTIFACTS / "customer_feedback.csv"
COMPARISON_JSON = ARTIFACTS / "usage_period_comparison.json"
NOTICE_MD = ARTIFACTS / "customer_group_notification_drafts.md"

STEPS = [
    ("双周期使用量对比", "usage_period_comparison"),
    ("账号健康度分类", "usage_health_classifier"),
    ("Qwen3 使用情况总结", "ai_usage_summary"),
    ("客户反馈分类", "feedback_router"),
    ("Qwen3 客户反馈总结", "ai_feedback_summary"),
    ("统一运营跟进表", "customer_operations_report"),
]


def run_module(label, module):
    print(f"\n===== {label} =====", flush=True)
    subprocess.run(
        [sys.executable, "-m", f"sp_workflow.flow_a.{module}"],
        cwd=ROOT,
        env={
            **__import__("os").environ,
            "PYTHONPATH": str(ROOT / "src"),
        },
        check=True,
    )


def write_group_notice():
    if not COMPARISON_JSON.exists():
        raise FileNotFoundError("缺少双周期对比结果，无法生成通知草稿。")

    data = json.loads(COMPARISON_JSON.read_text(encoding="utf-8"))
    companies = data.get("companies", [])
    if not companies:
        raise ValueError("对比结果没有公司记录。")

    lines = [
        "# 客户群通知草稿（待 CSM 审核）",
        "",
        "> 本文件仅生成草稿，不会发送到微信或其他社群。",
        "> 发送前请由 CSM 确认客户、数据周期和措辞。",
        "",
    ]

    for company in companies:
        name = company.get("company_name", "未命名客户")
        change = company.get("daily_average_change_percent")
        status = company.get("status")

        if change is None or status != "comparable":
            trend = "本期与上期数据暂不适合直接比较，请先核实数据。"
        elif change < 0:
            trend = f"团队日均使用量较上一周期下降 {abs(change):.2f}%。"
        elif change > 0:
            trend = f"团队日均使用量较上一周期上升 {change:.2f}%。"
        else:
            trend = "团队日均使用量与上一周期持平。"

        message = (
            "大家好，今天同步一下团队最近一个月的账号使用情况。"
            "我们通过 AI 助手标记了使用变化较明显的账号，供大家参考；"
            "每位同学的工作流和使用规划不同，数据变化不代表产品一定存在问题。"
            "如果遇到使用问题、希望了解更高效的使用方式，"
            "或有产品建议，欢迎直接在群里回复【使用问题】、【培训需求】"
            "或【产品建议】，CSM 会协助跟进！"
        )

        lines.extend([
            f"## {name}",
            "",
            f"- 内部趋势参考：{trend}",
            f"- 对比状态：{status}",
            "- 审核状态：待 CSM 审核",
            "",
            "### 客户群消息草稿",
            "",
            message,
            "",
            "---",
            "",
        ])

    NOTICE_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n客户群通知草稿：{NOTICE_MD}")


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    # First run creates an import template; never continue with stale feedback.
    if not FEEDBACK_CSV.exists():
        run_module("创建客户反馈导入模板", "feedback_router")
        print(
            "\n已创建客户反馈模板。请先填写反馈并重新运行，"
            "避免使用旧的反馈结果。"
        )
        return

    try:
        for label, module in STEPS:
            run_module(label, module)

        write_group_notice()

        print("\n===== Flow A 运行完成 =====")
        print(f"内部运营表：{ARTIFACTS / 'customer_followup_queue.csv'}")
        print(f"客户群通知草稿：{NOTICE_MD}")
        print("安全说明：没有发送客户消息、写入 CRM 或自动创建工单。")
        print("Skill 1 仅作为候选流程，仍须按现有规则审核。")
    except subprocess.CalledProcessError as exc:
        print(f"\n工作流中止：模块运行失败，退出码 {exc.returncode}")
        print("请先修复当前模块，再重新运行。")
        raise SystemExit(exc.returncode)


if __name__ == "__main__":
    main()
