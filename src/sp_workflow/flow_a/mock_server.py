
"""Flow A 本地模拟客户后台，仅用于浏览器自动化实验。"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import csv
import io
from html import escape


HOST = "127.0.0.1"
PORT = 8765

# 全部为虚构客户和演示数据
CUSTOMERS = [
    {
        "id": "C001",
        "name": "Demo Customer A",
        "business": "Sales A",
        "account": "demo_account_a",
        "email": "demo-a@example.com",
        "previous": 100,
        "current": 70,
    },
    {
        "id": "C002",
        "name": "Demo Customer B",
        "business": "Sales A",
        "account": "demo_account_b",
        "email": "demo-b@example.com",
        "previous": 80,
        "current": 76,
    },
    {
        "id": "C003",
        "name": "Demo Customer C",
        "business": "Sales B",
        "account": "demo_account_c",
        "email": "demo-c@example.com",
        "previous": 50,
        "current": 35,
    },
    {
        "id": "C004",
        "name": "Demo Customer D",
        "business": "Sales B",
        "account": "demo_account_d",
        "email": "demo-d@example.com",
        "previous": 0,
        "current": 0,
    },
]


def find_customer(customer_id):
    return next(
        (c for c in CUSTOMERS if c["id"] == customer_id),
        None,
    )


def page(title, body):
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 900px;
       margin: 40px auto; padding: 0 20px; color: #222; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
th {{ background: #f3f4f6; }}
a, button {{ cursor: pointer; }}
.notice {{ padding: 12px; background: #f3f4f6; border-radius: 8px; }}
</style>
</head>
<body>
<h1>{escape(title)}</h1>
{body}
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def send_html(self, html, status=200):
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            selected = query.get("business", ["All"])[0]
            businesses = sorted({c["business"] for c in CUSTOMERS})

            options = '<option value="All">全部商务</option>'
            for business in businesses:
                mark = " selected" if business == selected else ""
                options += (
                    f'<option value="{escape(business)}"{mark}>'
                    f'{escape(business)}</option>'
                )

            visible = [
                c for c in CUSTOMERS
                if selected == "All" or c["business"] == selected
            ]

            rows = ""
            for c in visible:
                rows += f"""
                <tr>
                  <td>{escape(c['id'])}</td>
                  <td><a href="/customer/{escape(c['id'])}">
                    {escape(c['name'])}</a></td>
                  <td>{escape(c['business'])}</td>
                  <td>{c['previous']}</td>
                  <td>{c['current']}</td>
                </tr>"""

            body = f"""
            <p class="notice">本地演示环境：所有客户均为虚构数据。</p>
            <form method="get" action="/">
              <label for="business">负责商务：</label>
              <select id="business" name="business">{options}</select>
              <button type="submit">筛选客户</button>
            </form>
            <table>
              <thead><tr>
                <th>客户 ID</th><th>客户名称</th><th>负责商务</th>
                <th>上上周使用次数</th><th>上周使用次数</th>
              </tr></thead>
              <tbody>{rows}</tbody>
            </table>"""
            return self.send_html(page("Flow A 客户管理后台", body))

        if path.startswith("/customer/"):
            customer_id = path.rsplit("/", 1)[-1]
            c = find_customer(customer_id)
            if not c:
                return self.send_html(page("未找到客户", "<p>客户不存在。</p>"), 404)

            body = f"""
            <p><strong>客户 ID：</strong>{escape(c['id'])}</p>
            <p><strong>客户名称：</strong>{escape(c['name'])}</p>
            <p><strong>负责商务：</strong>{escape(c['business'])}</p>
            <p><strong>账号：</strong>{escape(c['account'])}</p>
            <p><strong>邮箱：</strong>{escape(c['email'])}</p>
            <p><strong>上上周使用次数：</strong>{c['previous']}</p>
            <p><strong>上周使用次数：</strong>{c['current']}</p>
            <p><a href="/download/{escape(c['id'])}.csv"
                  download>下载使用数据 CSV</a></p>
            <p><a href="/">返回客户列表</a></p>"""
            return self.send_html(page(c["name"], body))

        if path.startswith("/download/") and path.endswith(".csv"):
            customer_id = path.rsplit("/", 1)[-1][:-4]
            c = find_customer(customer_id)
            if not c:
                return self.send_html(page("下载失败", "<p>客户不存在。</p>"), 404)

            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow([
                "customer_id", "customer_name", "business",
                "account", "email", "previous_week_usage",
                "current_week_usage",
            ])
            writer.writerow([
                c["id"], c["name"], c["business"], c["account"],
                c["email"], c["previous"], c["current"],
            ])
            data = output.getvalue().encode("utf-8-sig")

            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{c["id"]}.csv"',
            )
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_html(page("未找到页面", "<p>404 Not Found</p>"), 404)

    def log_message(self, format_string, *args):
        print("[模拟后台]", format_string % args)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"模拟后台已启动：http://{HOST}:{PORT}")
    print("按 Control + C 停止服务。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n模拟后台已停止。")
    finally:
        server.server_close()

