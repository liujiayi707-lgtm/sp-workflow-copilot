"""Classify customer usage health from Flow A comparison results."""

import csv
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT / "data" / "flow_a_demo"
CURRENT_DIR = DATA_DIR / "history" / "current"
ARTIFACT_DIR = ROOT / "artifacts" / "flow_a"

INPUT_JSON = ARTIFACT_DIR / "usage_period_comparison.json"
ROLE_FILE = DATA_DIR / "account_roles.json"
OUTPUT_JSON = ARTIFACT_DIR / "usage_health_classification.json"
OUTPUT_CSV = ARTIFACT_DIR / "usage_health_classification.csv"

LOW_USAGE_THRESHOLD = 10
DECLINE_THRESHOLD = 20
ZERO_STREAK_THRESHOLD = 5

COMPANIES = ["company-a.csv", "company-b.csv", "company-c.csv"]
IDENTITY_FIELDS = {"company_name", "sales", "user_id", "frequency_label"}


def number(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def load_roles():
    """Optional manually maintained account-role mapping."""
    if not ROLE_FILE.exists():
        return {}
    data = json.loads(ROLE_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("account_roles.json 必须是 JSON 对象")
    return data


def read_current_usage(filename):
    path = CURRENT_DIR / filename
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        date_columns = [
            h for h in headers if h not in IDENTITY_FIELDS
        ]
        dates = []
        for column in date_columns:
            try:
                dates.append((date.fromisoformat(column), column))
            except ValueError:
                continue

        result = {}
        for row in reader:
            user_id = (row.get("user_id") or "").strip()
            if not user_id:
                continue

            observations = []
            for day, column in sorted(dates):
                raw = (row.get(column) or "").strip()
                value = number(raw)
                observations.append({
                    "date": day,
                    "value": value,
                })

            zero_streak = 0
            max_zero_streak = 0
            previous_day = None

            for item in observations:
                day = item["date"]
                value = item["value"]

                # A missing/invalid value or a calendar date gap breaks
                # the streak; missing data must never count as zero.
                consecutive_day = (
                    previous_day is not None
                    and (day - previous_day).days == 1
                )

                if value == 0:
                    zero_streak = zero_streak + 1 if consecutive_day else 1
                    max_zero_streak = max(max_zero_streak, zero_streak)
                else:
                    zero_streak = 0

                previous_day = day

            result[user_id] = {
                "max_consecutive_zero_days": max_zero_streak,
                "current_observation_days": len(observations),
            }

        return result


def classify_account(row, current_usage, roles):
    user_id = str(row.get("user_id", ""))
    status = row.get("status", "unknown")
    role = roles.get(user_id, "unknown")

    current_avg = number(row.get("current_daily_average"))
    previous_avg = number(row.get("previous_daily_average"))
    change = number(row.get("daily_average_change_percent"))

    zero_days = current_usage.get(
        user_id, {}
    ).get("max_consecutive_zero_days", 0)

    risks = []
    actions = []
    caveats = []

    if status == "new_account":
        caveats.append("新账号，缺少上一周期基线")
        actions.append("确认账号用途及使用者")
    elif status in ("not_in_current_period", "not_in_current"):
        risks.append("账号未出现在当前周期导出中")
        caveats.append("无法仅凭导出结果确认账号是否被删除")
        actions.append("核实账号状态、筛选条件及导出权限")
    elif status in ("insufficient_data", "incomplete_data",
                    "incomparable_coverage"):
        caveats.append("双周期数据或覆盖范围需要核实")
        actions.append("核实数据完整性后再确认风险等级")

    # Long-term low usage requires both periods' daily averages.
    if current_avg is not None and previous_avg is not None:
        if current_avg < LOW_USAGE_THRESHOLD and previous_avg < LOW_USAGE_THRESHOLD:
            if role == "executive":
                caveats.append("管理层账号：低频需结合实际职责判断")
            else:
                risks.append("连续两个周期日均使用低于10次")
                actions.append("了解实际使用场景及培训需求")
    else:
        if status not in ("new_account", "not_in_current_period",
                          "not_in_current"):
            caveats.append("缺少足够的双周期日均数据，无法判断长期低频")

    # A percentage change is only a risk signal when the previous
    # baseline is positive and a numeric change has been calculated.
    if change is not None and change < -DECLINE_THRESHOLD:
        risks.append(f"日均使用量下降{abs(change):.2f}%")
        actions.append("联系客户确认近期使用情况及是否需要支持")

    if zero_days >= ZERO_STREAK_THRESHOLD:
        risks.append(f"当前周期存在连续{zero_days}天真实零使用")
        actions.append("由CSM核实使用情况、账号状态及是否需要支持")

        # 只有历史使用水平较高时，才自动提升核查优先级。
        # 长期低频账号保留风险信号，由CSM结合业务背景判断。
        if previous_avg is not None and previous_avg >= 100:
            actions.append("优先核实高频账号持续零使用的原因")

    if role == "unknown":
        caveats.append("账号角色未知；必要时由CSM确认")

    if not risks:
        risks.append("暂未发现符合当前规则的明确风险信号")

    if status not in ("comparable",):
        caveats.append(f"原始对比状态：{status}")

    if caveats and any(
        word in " ".join(caveats)
        for word in ("数据", "缺少", "覆盖", "原始对比状态")
    ):
        level = "待核实"
    elif (
        previous_avg is not None
        and previous_avg >= 100
        and zero_days >= ZERO_STREAK_THRESHOLD
    ):
        level = "高优先级核查"
    elif any(
        "下降" in risk or "低于10次" in risk for risk in risks
    ):
        level = "需要跟进"
    else:
        level = "常规观察"

    return {
        "company_name": row.get("company_name"),
        "sales": row.get("sales"),
        "user_id": user_id,
        "account_role": role,
        "comparison_status": status,
        "current_daily_average": current_avg,
        "previous_daily_average": previous_avg,
        "daily_average_change_percent": change,
        "max_consecutive_zero_days": zero_days,
        "risk_level": level,
        "risk_signals": risks,
        "recommended_actions": list(dict.fromkeys(actions)),
        "data_caveats": list(dict.fromkeys(caveats)),
    }


def main():
    if not INPUT_JSON.exists():
        raise FileNotFoundError(
            f"找不到 {INPUT_JSON}，请先运行 usage_period_comparison"
        )

    data = json.loads(INPUT_JSON.read_text(encoding="utf-8"))
    comparison_accounts = data.get("accounts", [])
    if not comparison_accounts:
        raise ValueError("对比 JSON 中没有账号记录")

    roles = load_roles()
    current_usage = {}
    for filename in COMPANIES:
        current_usage.update(read_current_usage(filename))

    results = [
        classify_account(
            row,
            current_usage,
            roles,
        )
        for row in comparison_accounts
    ]

    payload = {
        "rules": {
            "low_daily_usage_threshold": LOW_USAGE_THRESHOLD,
            "decline_threshold_percent": DECLINE_THRESHOLD,
            "zero_streak_days": ZERO_STREAK_THRESHOLD,
            "default_account_role": "unknown",
            "missing_values_are_zero": False,
            "note": "规则阈值为初始业务配置，需结合实际客户情况校准",
        },
        "accounts": results,
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fields = [
        "company_name", "sales", "user_id", "account_role",
        "comparison_status", "current_daily_average",
        "previous_daily_average", "daily_average_change_percent",
        "max_consecutive_zero_days", "risk_level",
        "risk_signals", "recommended_actions", "data_caveats",
    ]
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in results:
            writer.writerow({
                **row,
                "risk_signals": "；".join(row["risk_signals"]),
                "recommended_actions": "；".join(
                    row["recommended_actions"]
                ),
                "data_caveats": "；".join(row["data_caveats"]),
            })

    print("===== 客户使用健康度分类完成 =====")
    print(f"账号记录：{len(results)}")
    for company in sorted({
        row["company_name"] for row in results
    }):
        subset = [
            row for row in results
            if row["company_name"] == company
        ]
        print(
            f"{company}: {len(subset)} 个账号，"
            f"需要跟进 {sum(r['risk_level'] == '需要跟进' for r in subset)}，"
            f"高优先级核查 "
            f"{sum(r['risk_level'] == '高优先级核查' for r in subset)}，"
            f"待核实 {sum(r['risk_level'] == '待核实' for r in subset)}"
        )

    print(f"JSON：{OUTPUT_JSON}")
    print(f"CSV：{OUTPUT_CSV}")


if __name__ == "__main__":
    main()
