
"""Flow A: Compare usage totals and daily averages across periods."""

import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HISTORY_DIR = ROOT / "data" / "flow_a_demo" / "history"
PREVIOUS_DIR = HISTORY_DIR / "previous"
CURRENT_DIR = HISTORY_DIR / "current"
OUTPUT_DIR = ROOT / "artifacts" / "flow_a"

OUTPUT_JSON = OUTPUT_DIR / "usage_period_comparison.json"
OUTPUT_CSV = OUTPUT_DIR / "usage_period_comparison.csv"
OUTPUT_COMPANY_CSV = OUTPUT_DIR / "usage_company_comparison.csv"

THRESHOLD_PERCENT = 20.0
COMPANIES = ["company-a.csv", "company-b.csv", "company-c.csv"]

IDENTITY_FIELDS = {
    "company_name", "sales", "user_id", "frequency_label"
}


def parse_day(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def read_snapshot(path):
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        headers = reader.fieldnames or []
        rows = list(reader)

    if not IDENTITY_FIELDS.issubset(set(headers)):
        raise ValueError(f"{path.name}: 缺少必要字段")

    date_columns = [
        header for header in headers
        if header not in IDENTITY_FIELDS
    ]
    parsed_dates = [parse_day(day) for day in date_columns]

    if not date_columns or any(day is None for day in parsed_dates):
        raise ValueError(f"{path.name}: 日期列格式无效")

    if len(set(date_columns)) != len(date_columns):
        raise ValueError(f"{path.name}: 存在重复日期列")

    ordered_dates = sorted(parsed_dates)
    expected_dates = []
    cursor = ordered_dates[0]

    while cursor <= ordered_dates[-1]:
        expected_dates.append(cursor)
        cursor += timedelta(days=1)

    missing_date_columns = sorted(
        day.isoformat()
        for day in set(expected_dates) - set(ordered_dates)
    )

    accounts = {}

    for row in rows:
        user_id = (row.get("user_id") or "").strip()
        if not user_id:
            continue
        if user_id in accounts:
            raise ValueError(f"{path.name}: 重复用户 ID {user_id}")

        observations = {}
        missing_cells = 0
        invalid_cells = 0

        for column, day in zip(date_columns, parsed_dates):
            raw = (row.get(column) or "").strip()
            key = day.isoformat()

            if not raw:
                observations[key] = None
                missing_cells += 1
                continue

            try:
                number = float(raw)
                if number < 0 or not number.is_integer():
                    raise ValueError
                observations[key] = int(number)
            except ValueError:
                observations[key] = None
                invalid_cells += 1

        valid_values = [
            value for value in observations.values()
            if value is not None
        ]

        accounts[user_id] = {
            "company_name": row["company_name"],
            "sales": row["sales"],
            "user_id": user_id,
            "frequency_label": row["frequency_label"],
            "observations": observations,
            "total": sum(valid_values) if valid_values else None,
            "valid_days": len(valid_values),
            "missing_cells": missing_cells,
            "invalid_cells": invalid_cells,
        }

    if not accounts:
        raise ValueError(f"{path.name}: 没有账号记录")

    companies = {x["company_name"] for x in accounts.values()}
    sales = {x["sales"] for x in accounts.values()}
    if len(companies) != 1 or len(sales) != 1:
        raise ValueError(f"{path.name}: 公司或商务信息不一致")

    return {
        "company_name": next(iter(companies)),
        "sales": next(iter(sales)),
        "accounts": accounts,
        "date_columns": sorted(x.isoformat() for x in ordered_dates),
        "missing_date_columns": missing_date_columns,
    }


def is_complete(account, snapshot):
    return (
        account["total"] is not None
        and account["valid_days"] > 0
        and account["missing_cells"] == 0
        and account["invalid_cells"] == 0
        and not snapshot["missing_date_columns"]
    )


def compare_account(current, previous, current_snapshot, previous_snapshot):
    result = {
        "company_name": current["company_name"],
        "sales": current["sales"],
        "user_id": current["user_id"],
        "frequency_label": current["frequency_label"],
        "current_total": current["total"],
        "previous_total": previous["total"],
        "current_daily_average": None,
        "previous_daily_average": None,
        "total_change": None,
        "total_change_percent": None,
        "daily_average_change_percent": None,
        "status": "comparable",
        "data_complete": False,
        "alert_triggered": False,
    }

    # Compare the same date positions in each period. A date gap is
    # acceptable when the coverage pattern is identical in both periods.
    current_days = set(current["observations"])
    previous_days = set(previous["observations"])

    # The actual dates differ between periods, so compare the pattern
    # of missing cells and the number of valid observation days.
    same_coverage = (
        current["valid_days"] == previous["valid_days"]
        and current["missing_cells"] == previous["missing_cells"]
        and current["invalid_cells"] == previous["invalid_cells"]
        and len(current_snapshot["date_columns"])
        == len(previous_snapshot["date_columns"])
        and len(current_snapshot["missing_date_columns"])
        == len(previous_snapshot["missing_date_columns"])
    )

    complete = (
        is_complete(current, current_snapshot)
        and is_complete(previous, previous_snapshot)
    )

    # Matching incomplete records may be shown for context, but must
    # not trigger an alert unless the data is complete.
    if current["total"] is None or previous["total"] is None:
        result["status"] = "insufficient_data"
        return result

    if current["valid_days"] == 0 or previous["valid_days"] == 0:
        result["status"] = "insufficient_data"
        return result

    current_avg = current["total"] / current["valid_days"]
    previous_avg = previous["total"] / previous["valid_days"]

    result["current_daily_average"] = round(current_avg, 2)
    result["previous_daily_average"] = round(previous_avg, 2)
    result["data_complete"] = complete

    if previous["total"] == 0:
        result["status"] = (
            "both_periods_zero"
            if current["total"] == 0
            else "previous_period_zero"
        )
        return result

    result["total_change"] = current["total"] - previous["total"]
    result["total_change_percent"] = round(
        (current["total"] - previous["total"])
        / previous["total"] * 100,
        2,
    )

    if previous_avg == 0:
        result["status"] = (
            "both_daily_averages_zero"
            if current_avg == 0
            else "previous_daily_average_zero"
        )
        return result

    result["daily_average_change_percent"] = round(
        (current_avg - previous_avg) / previous_avg * 100,
        2,
    )

    if not same_coverage:
        result["status"] = "incomparable_coverage"
        return result

    if not complete:
        result["status"] = "incomplete_data"
        return result

    result["status"] = "comparable"
    result["alert_triggered"] = (
        result["daily_average_change_percent"] < -THRESHOLD_PERCENT
    )
    return result


def company_summary(company_name, sales, current, previous, account_results):
    # Only common accounts with valid usage totals in both periods
    # contribute to company-level comparison. New and missing accounts
    # are reported separately and do not distort the comparison base.
    comparable_ids = [
        user_id for user_id in set(current["accounts"])
        & set(previous["accounts"])
        if current["accounts"][user_id]["total"] is not None
        and previous["accounts"][user_id]["total"] is not None
        and current["accounts"][user_id]["valid_days"] > 0
        and previous["accounts"][user_id]["valid_days"] > 0
    ]

    current_total = sum(
        current["accounts"][uid]["total"] for uid in comparable_ids
    )
    previous_total = sum(
        previous["accounts"][uid]["total"] for uid in comparable_ids
    )
    current_days = sum(
        current["accounts"][uid]["valid_days"] for uid in comparable_ids
    )
    previous_days = sum(
        previous["accounts"][uid]["valid_days"] for uid in comparable_ids
    )

    current_avg = current_total / current_days if current_days else None
    previous_avg = previous_total / previous_days if previous_days else None

    total_change = None
    total_change_percent = None
    daily_change_percent = None
    status = "comparable"
    alert = False

    if not comparable_ids or not current_days or not previous_days:
        status = "insufficient_data"
    elif previous_total == 0:
        status = (
            "both_periods_zero"
            if current_total == 0
            else "previous_period_zero"
        )
    elif previous_avg == 0:
        status = (
            "both_daily_averages_zero"
            if current_avg == 0
            else "previous_daily_average_zero"
        )
    else:
        total_change = current_total - previous_total
        total_change_percent = round(
            total_change / previous_total * 100, 2
        )
        daily_change_percent = round(
            (current_avg - previous_avg) / previous_avg * 100, 2
        )

        # Incomplete accounts are excluded from the comparison base.
        # Their counts are exposed for CSM review instead of blocking
        # the remaining valid accounts.
        alert = daily_change_percent < -THRESHOLD_PERCENT

    new_ids = set(current["accounts"]) - set(previous["accounts"])
    absent_ids = set(previous["accounts"]) - set(current["accounts"])
    insufficient_ids = [
        row["user_id"] for row in account_results
        if row["company_name"] == company_name
        and row["status"] == "insufficient_data"
    ]

    return {
        "company_name": company_name,
        "sales": sales,
        "current_account_count": len(current["accounts"]),
        "previous_account_count": len(previous["accounts"]),
        "comparable_account_count": len(comparable_ids),
        "new_account_count": len(new_ids),
        "not_in_current_count": len(absent_ids),
        "insufficient_data_account_count": len(insufficient_ids),
        "current_total": current_total if comparable_ids else None,
        "previous_total": previous_total if comparable_ids else None,
        "total_change": total_change,
        "total_change_percent": total_change_percent,
        "current_daily_average": (
            round(current_avg, 2) if current_avg is not None else None
        ),
        "previous_daily_average": (
            round(previous_avg, 2) if previous_avg is not None else None
        ),
        "daily_average_change_percent": daily_change_percent,
        "status": status,
        "alert_triggered": alert,
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    current_snapshots = {}
    previous_snapshots = {}
    missing_files = []

    for filename in COMPANIES:
        current_path = CURRENT_DIR / filename
        previous_path = PREVIOUS_DIR / filename

        if not current_path.exists():
            raise FileNotFoundError(f"缺少当前周期文件：{current_path}")

        current_snapshots[filename] = read_snapshot(current_path)

        if previous_path.exists():
            previous_snapshots[filename] = read_snapshot(previous_path)
        else:
            missing_files.append(filename)

    account_results = []
    company_results = []

    for filename in COMPANIES:
        current = current_snapshots[filename]
        previous = previous_snapshots.get(filename)

        if previous is None:
            company_results.append({
                "company_name": current["company_name"],
                "sales": current["sales"],
                "current_account_count": len(current["accounts"]),
                "previous_account_count": None,
                "comparable_account_count": 0,
                "new_account_count": None,
                "not_in_current_count": None,
                "insufficient_data_account_count": None,
                "current_total": sum(
                    x["total"] or 0 for x in current["accounts"].values()
                ),
                "previous_total": None,
                "total_change": None,
                "total_change_percent": None,
                "current_daily_average": None,
                "previous_daily_average": None,
                "daily_average_change_percent": None,
                "status": "awaiting_previous_period",
                "alert_triggered": False,
            })
            continue

        if current["company_name"] != previous["company_name"]:
            raise ValueError(f"{filename}: 公司名称不一致")
        if current["sales"] != previous["sales"]:
            raise ValueError(f"{filename}: 商务归属不一致")

        current_ids = set(current["accounts"])
        previous_ids = set(previous["accounts"])

        for user_id in sorted(current_ids | previous_ids):
            now = current["accounts"].get(user_id)
            before = previous["accounts"].get(user_id)

            if now is None:
                account_results.append({
                    "company_name": previous["company_name"],
                    "sales": previous["sales"],
                    "user_id": user_id,
                    "frequency_label": before["frequency_label"],
                    "current_total": None,
                    "previous_total": before["total"],
                    "current_daily_average": None,
                    "previous_daily_average": (
                        round(before["total"] / before["valid_days"], 2)
                        if before["total"] is not None
                        and before["valid_days"] else None
                    ),
                    "total_change": None,
                    "total_change_percent": None,
                    "daily_average_change_percent": None,
                    "status": "not_in_current_period",
                    "data_complete": False,
                    "alert_triggered": False,
                })
                continue

            if before is None:
                account_results.append({
                    "company_name": now["company_name"],
                    "sales": now["sales"],
                    "user_id": user_id,
                    "frequency_label": now["frequency_label"],
                    "current_total": now["total"],
                    "previous_total": None,
                    "current_daily_average": (
                        round(now["total"] / now["valid_days"], 2)
                        if now["total"] is not None and now["valid_days"]
                        else None
                    ),
                    "previous_daily_average": None,
                    "total_change": None,
                    "total_change_percent": None,
                    "daily_average_change_percent": None,
                    "status": "new_account",
                    "data_complete": False,
                    "alert_triggered": False,
                })
                continue

            account_results.append(
                compare_account(now, before, current, previous)
            )

        company_results.append(
            company_summary(
                current["company_name"],
                current["sales"],
                current,
                previous,
                account_results,
            )
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "threshold_percent": THRESHOLD_PERCENT,
        "alert_metric": "daily_average_change_percent",
        "previous_period_files_missing": missing_files,
        "comparison_status": (
            "awaiting_previous_period"
            if missing_files else "comparison_generated"
        ),
        "rules": {
            "missing_values_are_zero": False,
            "missing_dates_are_zero": False,
            "new_accounts_trigger_decline_alert": False,
            "company_comparison_uses_common_accounts": True,
            "company_alert_requires_all_accounts_complete": False,
        },
        "companies": company_results,
        "accounts": account_results,
    }

    OUTPUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    def write_csv(path, rows):
        if not rows:
            return
        fields = list(dict.fromkeys(
            key for row in rows for key in row
        ))
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    write_csv(OUTPUT_CSV, account_results)
    write_csv(OUTPUT_COMPANY_CSV, company_results)

    print("===== 双周期对比 =====")
    print(f"预警阈值：日均使用量下降超过 {THRESHOLD_PERCENT}%")
    print(f"公司数：{len(company_results)}")
    print(f"账号对比记录：{len(account_results)}")

    for company in company_results:
        print(
            f"{company['company_name']}: "
            f"状态={company['status']}, "
            f"可比较账号={company['comparable_account_count']}, "
            f"日均变化率={company['daily_average_change_percent']}, "
            f"预警={company['alert_triggered']}"
        )

    if missing_files:
        print("\n缺少上一周期文件：", ", ".join(missing_files))

    print(f"\nJSON：{OUTPUT_JSON}")
    print(f"账号明细：{OUTPUT_CSV}")
    print(f"公司汇总：{OUTPUT_COMPANY_CSV}")


if __name__ == "__main__":
    main()
