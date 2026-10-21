"""Route customer feedback to suggested Customer Success actions."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = ROOT / "artifacts" / "flow_a"

INPUT_FILE = ARTIFACT_DIR / "customer_feedback.csv"
OUTPUT_JSON = ARTIFACT_DIR / "customer_feedback_routing.json"
OUTPUT_CSV = ARTIFACT_DIR / "customer_feedback_routing.csv"

# 初版采用可解释的关键词规则。
# 分类结果是建议，不代表已确认的产品问题。
ROUTES = [
    {
        "category": "suspected_product_issue",
        "label": "疑似产品问题",
        "keywords": [
            "bug", "报错", "报错了", "打不开", "无法打开",
            "数据错误", "数据不对", "数据丢失", "加载失败",
            "功能异常", "页面异常", "接口异常", "系统异常",
        ],
        "action": "整理问题描述、影响范围及发生时间，交由CSM核实；确认后可转入Skill 1。",
        "priority": "优先核实",
    },
    {
        "category": "usage_problem",
        "label": "使用问题",
        "keywords": [
            "不会用", "怎么用", "找不到", "不会操作",
            "使用困难", "使用问题", "查询不到", "不知道怎么",
        ],
        "action": "由CSM联系客户，了解具体操作步骤并提供指导。",
        "priority": "待CSM跟进",
    },
    {
        "category": "training_request",
        "label": "培训需求",
        "keywords": [
            "培训", "演示", "教学", "学习功能",
            "讲解一下", "线上交流", "培训一下",
        ],
        "action": "由CSM确认参与人员、目标功能和合适时间，评估是否安排培训或会议。",
        "priority": "待安排",
    },
    {
        "category": "feature_request",
        "label": "产品建议或业务需求",
        "keywords": [
            "希望增加", "建议增加", "新需求", "能不能支持",
            "希望支持", "产品建议", "功能建议", "需求",
        ],
        "action": "记录客户原话、使用场景及预期价值，交由CSM评估并视情况转交产品团队。",
        "priority": "待评估",
    },
    {
        "category": "normal_usage",
        "label": "正常使用",
        "keywords": [
            "一切正常", "使用正常", "没问题", "没有问题",
            "正常使用", "暂时不需要",
        ],
        "action": "记录客户反馈，按常规节奏持续关注。",
        "priority": "常规记录",
    },
    {
        "category": "needs_clarification",
        "label": "需要进一步了解",
        "keywords": [],
        "action": "由CSM进一步询问具体情况，不自动推断问题原因。",
        "priority": "待确认",
    },
]


def classify_feedback(message):
    normalized = (message or "").strip().lower()

    if not normalized:
        route = ROUTES[-1]
    else:
        # 分类优先级：产品问题 > 培训需求 > 使用问题 > 产品建议
        priority_order = [
            "suspected_product_issue",
            "training_request",
            "usage_problem",
            "feature_request",
            "normal_usage",
        ]
        route_by_category = {
            item["category"]: item for item in ROUTES
        }
        route = next(
            (
                route_by_category[category]
                for category in priority_order
                if any(
                    keyword.lower() in normalized
                    for keyword in route_by_category[category]["keywords"]
                )
            ),
            ROUTES[-1],
        )

    return {
        "category": route["category"],
        "category_label": route["label"],
        "suggested_action": route["action"],
        "priority": route["priority"],
        "requires_human_review": True,
    }


def main():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    if not INPUT_FILE.exists():
        with INPUT_FILE.open(
            "w", encoding="utf-8-sig", newline=""
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=[
                    "company_name",
                    "sales",
                    "feedback_source",
                    "customer_message",
                    "received_at",
                ],
            )
            writer.writeheader()

        print(f"已创建反馈导入模板：{INPUT_FILE}")
        print("请填入测试反馈后重新运行本模块。")
        return

    results = []
    with INPUT_FILE.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        for row in csv.DictReader(file):
            message = (row.get("customer_message") or "").strip()
            if not message:
                continue

            classification = classify_feedback(message)
            results.append({
                "company_name": row.get("company_name", ""),
                "sales": row.get("sales", ""),
                "feedback_source": row.get("feedback_source", ""),
                "customer_message": message,
                "received_at": row.get("received_at", ""),
                **classification,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "status": "pending_human_review",
            })

    OUTPUT_JSON.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fields = [
        "company_name", "sales", "feedback_source",
        "customer_message", "received_at", "category",
        "category_label", "suggested_action", "priority",
        "requires_human_review", "created_at", "status",
    ]
    with OUTPUT_CSV.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    print("===== 客户反馈分流完成 =====")
    print(f"处理反馈数：{len(results)}")
    for row in results:
        print(
            f"{row['company_name']} | "
            f"{row['category_label']} | "
            f"{row['priority']} | "
            f"{row['customer_message'][:50]}"
        )

    print(f"JSON：{OUTPUT_JSON}")
    print(f"CSV：{OUTPUT_CSV}")
    print("所有结果均待人工审核；未发送消息，也未创建真实工单。")


if __name__ == "__main__":
    main()
