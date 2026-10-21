"""Combine existing Flow A outputs into an internal report and follow-up queue."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = ROOT / "artifacts" / "flow_a"

INPUTS = {
    "comparison": ARTIFACT_DIR / "usage_period_comparison.json",
    "health": ARTIFACT_DIR / "usage_health_classification.json",
    "usage_ai": ARTIFACT_DIR / "ai_usage_summary.json",
    "feedback": ARTIFACT_DIR / "customer_feedback_routing.json",
    "feedback_ai": ARTIFACT_DIR / "ai_feedback_summary.json",
}

OUTPUT_JSON = ARTIFACT_DIR / "customer_operations_report.json"
OUTPUT_MD = ARTIFACT_DIR / "customer_operations_report.md"
OUTPUT_CSV = ARTIFACT_DIR / "customer_followup_queue.csv"

NO_RISK_LEVELS = {"正常", "低风险", "无需跟进", "无风险"}


def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"缺少必要文件：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def display(value):
    if value is None or value == "":
        return "未提供"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def join_feedback_ai(feedbacks, ai_rows):
    """Match feedback summaries by company, category and original message."""
    index = {}
    for row in ai_rows:
        key = (
            row.get("company_name"),
            row.get("category"),
            row.get("customer_message"),
        )
        index.setdefault(key, []).append(row)

    matched = []
    for feedback in feedbacks:
        key = (
            feedback.get("company_name"),
            feedback.get("category"),
            feedback.get("customer_message"),
        )
        candidates = index.get(key, [])
        ai = candidates.pop(0) if candidates else {}
        matched.append({**feedback, "ai": ai})
    return matched


def main():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    comparison = load_json(INPUTS["comparison"])
    health_data = load_json(INPUTS["health"])
    usage_ai = load_json(INPUTS["usage_ai"])
    feedback_data = load_json(INPUTS["feedback"])
    feedback_ai = load_json(INPUTS["feedback_ai"])

    companies = comparison.get("companies", [])
    accounts = comparison.get("accounts", [])
    health_accounts = health_data.get("accounts", [])

    if not companies:
        raise ValueError("周期对比结果中没有公司记录。")

    health_index = {
        (row.get("company_name"), row.get("user_id")): row
        for row in health_accounts
    }
    usage_ai_index = {
        row.get("company_name"): row for row in usage_ai
    }

    feedbacks = join_feedback_ai(feedback_data, feedback_ai)

    company_reports = []
    followups = []

    # Account-level follow-up tasks.
    for account in health_accounts:
        risk_level = account.get("risk_level")
        signals = account.get("risk_signals")
        has_signals = bool(signals) and signals != [
            "暂未发现符合当前规则的明确风险信号"
        ]

        if risk_level in NO_RISK_LEVELS and not has_signals:
            continue

        actions = account.get("recommended_actions")
        followups.append({
            "company_name": account.get("company_name"),
            "sales": account.get("sales"),
            "item_type": "账号健康度",
            "user_id": account.get("user_id"),
            "risk_level": risk_level,
            "risk_signals": display(signals),
            "data_caveats": display(account.get("data_caveats")),
            "source": "usage_health_classification",
            "category": "",
            "customer_message": "",
            "priority": risk_level or "待核实",
            "suggested_action": display(actions),
            "internal_summary": "",
            "missing_information": "",
            "skill1_candidate": False,
            "review_status": "pending_human_review",
            "followup_status": "待CSM判断",
        })

    # Feedback-level follow-up tasks. Normal usage is retained in the
    # company report but does not automatically create an action task.
    for feedback in feedbacks:
        ai = feedback.get("ai") or {}
        category = feedback.get("category")

        if category == "normal_usage":
            continue

        skill_candidate = (
            category == "suspected_product_issue"
            and ai.get("skill1_candidate") is True
        )

        followups.append({
            "company_name": feedback.get("company_name"),
            "sales": feedback.get("sales"),
            "item_type": "客户反馈",
            "user_id": "",
            "risk_level": "",
            "risk_signals": "",
            "data_caveats": "",
            "source": "customer_feedback",
            "category": feedback.get("category_label") or category,
            "customer_message": feedback.get("customer_message"),
            "priority": feedback.get("priority"),
            "suggested_action": (
                ai.get("recommended_action")
                or feedback.get("suggested_action")
            ),
            "internal_summary": ai.get("internal_summary"),
            "missing_information": display(
                ai.get("missing_information")
            ),
            "skill1_candidate": skill_candidate,
            "review_status": ai.get(
                "review_status", "pending_human_review"
            ),
            "followup_status": "待CSM审核",
        })

    for company in companies:
        name = company.get("company_name")
        company_accounts = [
            row for row in accounts
            if row.get("company_name") == name
        ]
        company_health = [
            row for row in health_accounts
            if row.get("company_name") == name
        ]
        company_feedback = [
            row for row in feedbacks
            if row.get("company_name") == name
        ]
        ai = usage_ai_index.get(name, {})

        report = {
            "company_name": name,
            "sales": company.get("sales"),
            "comparison": company,
            "health_accounts": company_health,
            "usage_ai_summary": ai.get("summary"),
            "usage_ai_status": ai.get("generation_status"),
            "feedback": company_feedback,
            "account_comparison_count": len(company_accounts),
            "account_followup_count": sum(
                row.get("company_name") == name
                and row.get("item_type") == "账号健康度"
                for row in followups
            ),
            "feedback_followup_count": sum(
                row.get("company_name") == name
                and row.get("item_type") == "客户反馈"
                for row in followups
            ),
        }
        company_reports.append(report)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_status": "draft_pending_human_review",
        "company_count": len(company_reports),
        "account_followup_count": sum(
            row["item_type"] == "账号健康度" for row in followups
        ),
        "feedback_followup_count": sum(
            row["item_type"] == "客户反馈" for row in followups
        ),
        "companies": company_reports,
        "followups": followups,
        "notes": [
            "本报告整合已有文件，不重新计算使用量或调用模型。",
            "账号风险等级沿用健康度分类模块的结果。",
            "AI 内容均为草稿，须由 CSM 审核。",
            "Skill 1 候选不代表已调用 Skill 1。",
            "本模块不会发送消息、创建真实工单或修改 CRM。",
        ],
    }

    OUTPUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Enrich each follow-up row with its company's usage overview.
    company_index = {
        row.get("company_name"): row for row in companies
    }

    overview_fields = {
        "company_current_account_count": "current_account_count",
        "company_previous_account_count": "previous_account_count",
        "company_comparable_account_count": "comparable_account_count",
        "company_new_account_count": "new_account_count",
        "company_insufficient_data_count": "insufficient_data_account_count",
        "company_current_daily_average": "current_daily_average",
        "company_previous_daily_average": "previous_daily_average",
        "company_daily_average_change_percent": "daily_average_change_percent",
        "company_alert_triggered": "alert_triggered",
        "company_comparison_status": "status",
    }

    for row in followups:
        company = company_index.get(row.get("company_name"), {})
        for output_field, source_field in overview_fields.items():
            row[output_field] = company.get(source_field)

    # Keep a company overview row even when no follow-up task exists.
    companies_with_tasks = {
        row.get("company_name") for row in followups
    }

    for company in companies:
        name = company.get("company_name")
        if name in companies_with_tasks:
            continue

        row = {
            "company_name": name,
            "sales": company.get("sales"),
            "item_type": "公司概况",
            "user_id": "",
            "risk_level": "",
            "risk_signals": "",
            "data_caveats": "",
            "source": "usage_period_comparison",
            "category": "",
            "customer_message": "",
            "priority": "",
            "suggested_action": "当前没有独立跟进任务；按常规节奏关注。",
            "internal_summary": "",
            "missing_information": "",
            "skill1_candidate": False,
            "review_status": "not_applicable",
            "followup_status": "仅供概览",
        }
        for output_field, source_field in overview_fields.items():
            row[output_field] = company.get(source_field)
        followups.append(row)

    fields = [
        "company_name", "sales",
        "company_current_account_count",
        "company_previous_account_count",
        "company_comparable_account_count",
        "company_new_account_count",
        "company_insufficient_data_count",
        "company_current_daily_average",
        "company_previous_daily_average",
        "company_daily_average_change_percent",
        "company_alert_triggered",
        "company_comparison_status",
        "item_type", "user_id", "risk_level", "risk_signals",
        "data_caveats", "source", "category", "customer_message",
        "priority", "suggested_action", "internal_summary",
        "missing_information", "skill1_candidate",
        "review_status", "followup_status",
    ]
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(followups)

    print("===== 客户运营报告整合完成 =====")
    print(f"公司数：{len(company_reports)}")
    print(f"账号跟进记录：{payload['account_followup_count']}")
    print(f"客户反馈跟进记录：{payload['feedback_followup_count']}")
    print(f"Markdown：{OUTPUT_MD}")
    print(f"JSON：{OUTPUT_JSON}")
    print(f"跟进清单 CSV：{OUTPUT_CSV}")
    print("未调用模型、未发送消息、未创建工单或修改 CRM。")


if __name__ == "__main__":
    main()
