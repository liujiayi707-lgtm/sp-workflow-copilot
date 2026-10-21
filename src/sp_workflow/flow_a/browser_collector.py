
"""Flow A: Collect anonymized usage exports from the local demo portal."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BASE_URL = "http://127.0.0.1:8766"

# Separate output paths: preserve the original C001/C002 demo results.
DOWNLOAD_DIR = PROJECT_ROOT / "artifacts" / "flow_a" / "realdata_downloads"
LOG_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "flow_a"
    / "realdata_collection_log.json"
)

BUSINESSES = ["Sales A", "Sales B", "Sales C"]


def main():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(accept_downloads=True)

        try:
            for business in BUSINESSES:
                print(f"\n===== 开始处理 {business} =====")

                try:
                    page.goto(BASE_URL, wait_until="domcontentloaded")
                    page.locator("#business").select_option(business)
                    page.get_by_role("button", name="筛选客户").click()
                    page.wait_for_load_state("domcontentloaded")

                    links = page.locator('a[href^="/customer/"]')
                    hrefs = list(dict.fromkeys(
                        links.evaluate_all(
                            "(elements) => elements.map(e => e.getAttribute('href'))"
                        )
                    ))

                    print(f"找到客户数：{len(hrefs)}")

                    for href in hrefs:
                        slug = href.rstrip("/").split("/")[-1]
                        result = {
                            "business": business,
                            "customer": slug,
                            "status": "failed",
                            "filename": None,
                            "error": None,
                            "completed_at": None,
                        }

                        try:
                            page.goto(
                                f"{BASE_URL}{href}",
                                wait_until="domcontentloaded",
                            )

                            download_link = page.get_by_role(
                                "link", name="下载使用数据 CSV"
                            )

                            with page.expect_download(timeout=15000) as info:
                                download_link.click()

                            download = info.value
                            filename = f"{slug}.csv"
                            destination = DOWNLOAD_DIR / filename
                            download.save_as(str(destination))

                            if (
                                not destination.exists()
                                or destination.stat().st_size == 0
                            ):
                                raise RuntimeError("文件不存在或为空")

                            with destination.open(
                                "r", encoding="utf-8-sig", newline=""
                            ) as file:
                                reader = csv.DictReader(file)
                                rows = list(reader)
                                headers = reader.fieldnames or []

                            required = {
                                "company_name",
                                "sales",
                                "user_id",
                                "frequency_label",
                            }
                            if not required.issubset(set(headers)):
                                raise RuntimeError("CSV 缺少必要字段")

                            expected_rows = {
                                "Sales A": 5,
                                "Sales B": 9,
                                "Sales C": 4,
                            }[business]

                            if len(rows) != expected_rows:
                                raise RuntimeError(
                                    f"账号数量不符：预期 {expected_rows}，"
                                    f"实际 {len(rows)}"
                                )

                            if any(row.get("sales") != business for row in rows):
                                raise RuntimeError("CSV 中商务归属不一致")

                            if any(
                                not row.get("user_id")
                                for row in rows
                            ):
                                raise RuntimeError("发现空用户 ID")

                            result["status"] = "success"
                            result["filename"] = filename
                            result["account_count"] = len(rows)
                            result["date_column_count"] = len(headers) - 4

                        except Exception as exc:
                            result["error"] = (
                                f"{type(exc).__name__}: {exc}"
                            )

                        result["completed_at"] = datetime.now(
                            timezone.utc
                        ).isoformat()

                        results.append(result)

                        print(
                            f"{slug}: {result['status']}"
                            + (
                                f" — {result['error']}"
                                if result["error"]
                                else (
                                    f" — {result['account_count']} 个账号，"
                                    f"{result['date_column_count']} 个日期列"
                                )
                            )
                        )

                except Exception as exc:
                    results.append({
                        "business": business,
                        "customer": None,
                        "status": "failed",
                        "filename": None,
                        "error": f"{type(exc).__name__}: {exc}",
                        "completed_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                    })
                    print(f"{business} 筛选失败：{exc}")

        finally:
            browser.close()

    LOG_PATH.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    success = sum(item["status"] == "success" for item in results)
    failed = len(results) - success

    print("\n===== 真实脱敏数据采集汇总 =====")
    print(f"处理结果数：{len(results)}")
    print(f"成功：{success}")
    print(f"失败：{failed}")
    print(f"下载目录：{DOWNLOAD_DIR}")
    print(f"执行日志：{LOG_PATH}")


if __name__ == "__main__":
    main()
