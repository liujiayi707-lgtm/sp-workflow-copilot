"""Generate internal CRM notes and customer reply drafts using local Qwen3."""

import csv
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = ROOT / "artifacts" / "flow_a"
INPUT_FILE = ARTIFACT_DIR / "customer_feedback_routing.json"
OUTPUT_JSON = ARTIFACT_DIR / "ai_feedback_summary.json"
OUTPUT_MD = ARTIFACT_DIR / "ai_feedback_summary.md"
OUTPUT_CRM_CSV = ARTIFACT_DIR / "crm_followup_drafts.csv"

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen3:4b"
TIMEOUT_SECONDS = 180


SYSTEM_PROMPT = """
你是 B2B SaaS 客户成功经理的 AI 助手，服务对象是 SocialPeta 客户。

你需要根据客户原话、已有分类结果和建议动作，生成内部 CRM 跟进记录及外部回复草稿。

严格遵守：
1. 只能依据输入事实，不得编造客户背景、问题原因、处理结果或承诺。
2. 客户反馈分类是初步判断，不等于事实已经核实。
3. 不要将使用频率低直接解释为客户不满意或产品故障。
4. 如果信息不足，明确列出需要进一步确认的信息。
5. 如果疑似产品问题，建议 CSM 收集信息并核实；只有核实后才考虑调用 Skill 1。
6. 培训和需求类反馈应给出实际、可执行的下一步建议。
7. 外部回复要自然、礼貌、简洁，不暴露内部风险评级、AI判断或CRM记录。
8. 不要声称消息已经发送、工单已经创建或问题已经解决。
9. 不要输出思考过程，只输出 JSON。
10. 所有输出均使用中文。

严格返回以下 JSON 对象，不要附加 Markdown 代码围栏：
{
  "internal_summary": "简洁的内部情况摘要",
  "evidence": ["输入中有依据的事实"],
  "missing_information": ["需要进一步确认的信息"],
  "recommended_action": "建议的下一步动作",
  "suggested_owner": "建议负责角色，例如 CSM 或待确认",
  "skill1_candidate": false,
  "customer_reply_draft": "面向客户的回复草稿"
}

skill1_candidate 仅在客户原话明确描述疑似产品异常时设为 true。
这只表示建议进一步核实，不表示已调用 Skill 1。
"""


def call_qwen(feedback):
    facts = {
        "company_name": feedback.get("company_name"),
        "sales": feedback.get("sales"),
        "feedback_source": feedback.get("feedback_source"),
        "customer_message": feedback.get("customer_message"),
        "received_at": feedback.get("received_at"),
        "category": feedback.get("category"),
        "category_label": feedback.get("category_label"),
        "suggested_action_from_rules": feedback.get("suggested_action"),
        "priority_from_rules": feedback.get("priority"),
        "human_review_required": True,
    }

    payload = {
        "model": MODEL,
        "stream": False,
        "think": False,
        "format": {
            "type": "object",
            "properties": {
                "internal_summary": {"type": "string"},
                "evidence": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "missing_information": {
                    "type": "array",
                    "items": {"type": "string"}
                },
                "recommended_action": {"type": "string"},
                "suggested_owner": {"type": "string"},
                "skill1_candidate": {"type": "boolean"},
                "customer_reply_draft": {"type": "string"}
            },
            "required": [
                "internal_summary",
                "evidence",
                "missing_information",
                "recommended_action",
                "suggested_owner",
                "skill1_candidate",
                "customer_reply_draft"
            ],
            "additionalProperties": False
        },
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "请根据以下反馈生成内部记录和客户回复草稿：\n"
                    + json.dumps(facts, ensure_ascii=False)
                ),
            },
        ],
        "options": {
            "temperature": 0.1,
            "num_predict": 500,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(
        request, timeout=TIMEOUT_SECONDS
    ) as response:
        result = json.loads(response.read().decode("utf-8"))

    content = result.get("message", {}).get("content", "").strip()
    if not content:
        raise RuntimeError("Qwen3 未返回内容")

    parsed = json.loads(content)

    required = [
        "internal_summary",
        "evidence",
        "missing_information",
        "recommended_action",
        "suggested_owner",
        "skill1_candidate",
        "customer_reply_draft",
    ]
    missing = [key for key in required if key not in parsed]
    if missing:
        raise ValueError(
            "AI 返回结果缺少字段："
            + ", ".join(missing)
            + "\\n实际返回字段："
            + repr(list(parsed.keys()))
            + "\\n实际返回内容："
            + content[:2000]
        )

    if not isinstance(parsed["skill1_candidate"], bool):
        raise ValueError("skill1_candidate 必须为布尔值")

    # Only suspected product issues can be candidates for Skill 1.
    # Deterministic routing: suspected product issues enter
    # the Skill 1 candidate queue for review. This does not invoke Skill 1.
    parsed["skill1_candidate"] = (
        feedback.get("category") == "suspected_product_issue"
    )

    return parsed


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"找不到分类结果：{INPUT_FILE}\n"
            "请先运行 feedback_router。"
        )

    feedbacks = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    results = []

    for index, feedback in enumerate(feedbacks, start=1):
        company = feedback.get("company_name", "未知公司")
        print(f"正在生成 AI 总结：{company} ({index}/{len(feedbacks)})")

        try:
            ai = call_qwen(feedback)
            status = "success"
        except Exception as exc:
            ai = {
                "internal_summary": "AI 总结暂未生成，需人工处理。",
                "evidence": [feedback.get("customer_message", "")],
                "missing_information": [],
                "recommended_action": (
                    "检查 Ollama 是否运行及模型是否可用，然后重试。"
                ),
                "suggested_owner": "CSM",
                "skill1_candidate": False,
                "customer_reply_draft": "",
                "error_type": type(exc).__name__,
            }
            status = "failed"

        results.append({
            "company_name": company,
            "sales": feedback.get("sales"),
            "feedback_source": feedback.get("feedback_source"),
            "customer_message": feedback.get("customer_message"),
            "category": feedback.get("category"),
            "category_label": feedback.get("category_label"),
            "priority": feedback.get("priority"),
            "ai_status": status,
            **ai,
            "review_status": "pending_human_review",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"  结果：{status}")

    OUTPUT_JSON.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# Flow A：AI 客户反馈总结",
        "",
        f"模型：{MODEL}（本地 Ollama）",
        "",
        "> 所有内部记录和客户回复均为草稿，须经人工审核。",
        "",
    ]

    for row in results:
        lines.extend([
            f"## {row['company_name']} / {row.get('sales') or ''}",
            "",
            f"- 原始分类：{row.get('category_label')}",
            f"- AI 生成状态：{row['ai_status']}",
            f"- 客户原话：{row.get('customer_message')}",
            "",
            "### 内部 CRM 跟进记录",
            row["internal_summary"],
            "",
            "**事实依据**",
            *[f"- {x}" for x in row["evidence"]],
            "",
            "**待确认信息**",
            *[f"- {x}" for x in row["missing_information"]],
            "",
            f"**建议动作：** {row['recommended_action']}",
            f"**建议负责人：** {row['suggested_owner']}",
            f"**Skill 1 候选：** {row['skill1_candidate']}",
            "",
            "### 客户回复草稿",
            row["customer_reply_draft"] or "暂未生成，请人工起草。",
            "",
            f"**审核状态：** {row['review_status']}",
            "",
            "---",
            "",
        ])

    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")

    crm_fields = [
        "company_name", "sales", "customer_message",
        "category_label", "internal_summary", "recommended_action",
        "suggested_owner", "skill1_candidate", "review_status",
    ]
    with OUTPUT_CRM_CSV.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=crm_fields)
        writer.writeheader()
        for row in results:
            writer.writerow({
                key: row.get(key, "") for key in crm_fields
            })

    print("\n===== AI 反馈总结完成 =====")
    print(f"成功：{sum(x['ai_status'] == 'success' for x in results)}")
    print(f"失败：{sum(x['ai_status'] == 'failed' for x in results)}")
    print(f"JSON：{OUTPUT_JSON}")
    print(f"Markdown：{OUTPUT_MD}")
    print(f"CRM 草稿 CSV：{OUTPUT_CRM_CSV}")
    print("未发送客户消息，未创建真实工单，未自动调用 Skill 1。")


if __name__ == "__main__":
    main()
