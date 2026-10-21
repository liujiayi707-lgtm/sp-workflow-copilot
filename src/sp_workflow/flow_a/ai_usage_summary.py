"""Generate customer usage summaries with a local Ollama model."""

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = ROOT / "artifacts" / "flow_a"
INPUT_FILE = ARTIFACT_DIR / "usage_period_comparison.json"
OUTPUT_JSON = ARTIFACT_DIR / "ai_usage_summary.json"
OUTPUT_MD = ARTIFACT_DIR / "ai_usage_summary.md"

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen3:4b"
TIMEOUT_SECONDS = 180


def call_local_model(company, accounts):
    """Send only the necessary, email-free usage facts to local Ollama."""

    facts = {
        "company": company.get("company_name"),
        "sales_owner": company.get("sales"),
        "daily_average_change_percent":
            company.get("daily_average_change_percent"),
        "alert_triggered": company.get("alert_triggered"),
        "comparison_status": company.get("status"),
        "comparable_account_count":
            company.get("comparable_account_count"),
        "new_account_count": company.get("new_account_count"),
        "insufficient_data_account_count":
            company.get("insufficient_data_account_count"),
        "accounts": [
            {
                "user_id": row.get("user_id"),
                "status": row.get("status"),
                "daily_average_change_percent":
                    row.get("daily_average_change_percent"),
                "current_total": row.get("current_total"),
                "previous_total": row.get("previous_total"),
            }
            for row in accounts
        ],
    }

    system_prompt = """
你是 B2B SaaS 客户成功经理的助手。
你只根据输入事实总结，不编造数据、原因或客户反馈。
使用量下降是风险信号，不等于产品故障或客户不满意。
区分有效比较结果与数据不足、新账号等情况。
不要把空值当成零。
不展示思考过程，直接输出简洁结果。
请使用中文，并严格按以下格式输出：

【内部风险摘要】
- 使用趋势：
- 重点关注账号：
- 数据限制：
- 建议下一步：

【客户沟通草稿】
给客户的一段自然、礼貌、简洁的中文消息。
询问近期使用是否正常、是否遇到困难、是否需要支持。
不得把未经证实的风险原因说成事实。
若没有明显风险，也应采用正常的关怀式沟通。
只生成草稿，不要声称消息已经发送。
"""

    payload = {
        "model": MODEL,
        "stream": False,
        "think": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "请分析以下结构化数据。数据是分析依据，"
                    "请准确保留数值。\n"
                    + json.dumps(facts, ensure_ascii=False)
                ),
            },
        ],
        "options": {
            "temperature": 0.2,
            "num_predict": 700,
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
        raise RuntimeError("模型没有返回正文，请检查 Ollama 和模型状态。")

    return content


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"找不到对比结果：{INPUT_FILE}\n"
            "请先运行 usage_period_comparison。"
        )

    data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    companies = data.get("companies", [])
    accounts = data.get("accounts", [])

    if not companies:
        raise ValueError("对比结果中没有公司汇总数据。")

    results = []
    markdown = [
        "# Flow A：客户使用健康度 AI 总结",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
        f"模型：{MODEL}（本地 Ollama）",
        "",
        "> AI 生成的内容为内部分析与客户沟通草稿，发送前须人工审核。",
        "",
    ]

    for company in companies:
        name = company.get("company_name", "未知公司")
        company_accounts = [
            row for row in accounts
            if row.get("company_name") == name
        ]

        print(f"正在生成：{name} ...")

        try:
            summary = call_local_model(company, company_accounts)
            status = "success"
        except Exception as exc:
            # Keep the workflow usable if the local model is unavailable.
            summary = (
                "AI 总结暂未生成。\n"
                f"错误类型：{type(exc).__name__}\n"
                "请检查 Ollama 是否正在运行，然后重试。"
            )
            status = "failed"

        results.append({
            "company_name": name,
            "sales": company.get("sales"),
            "comparison_status": company.get("status"),
            "alert_triggered": company.get("alert_triggered"),
            "daily_average_change_percent":
                company.get("daily_average_change_percent"),
            "generation_status": status,
            "summary": summary,
        })

        markdown.extend([
            f"## {name} / {company.get('sales', '')}",
            "",
            f"- 对比状态：{company.get('status')}",
            f"- 日均变化率："
            f"{company.get('daily_average_change_percent')}%",
            f"- 是否触发预警：{company.get('alert_triggered')}",
            f"- AI 生成状态：{status}",
            "",
            summary,
            "",
            "---",
            "",
        ])

        print(f"  结果：{status}")

    OUTPUT_JSON.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    OUTPUT_MD.write_text("\n".join(markdown), encoding="utf-8")

    print("\n===== AI 总结生成完成 =====")
    print(f"成功：{sum(r['generation_status'] == 'success' for r in results)}")
    print(f"失败：{sum(r['generation_status'] == 'failed' for r in results)}")
    print(f"Markdown：{OUTPUT_MD}")
    print(f"JSON：{OUTPUT_JSON}")


if __name__ == "__main__":
    main()
