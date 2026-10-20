
"""
SocialPeta Workflow Copilot
共享模拟数据库：客户群消息、反馈记录、后续消息
第一版：仅操作本地 SQLite，不接入微信，不修改原始 Excel。
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone


# 项目根目录：SP Workflow Copilot
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# 独立模拟数据库，不覆盖任何原始 Excel
DB_PATH = PROJECT_ROOT / "data" / "sp_workflow_demo.db"


def get_connection():
    """创建数据库连接，并启用外键约束。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """初始化共享数据库表。"""
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_code TEXT NOT NULL,
                group_code TEXT,
                sender TEXT,
                message_text TEXT NOT NULL,
                received_at TEXT NOT NULL,
                category TEXT NOT NULL,
                should_send_template INTEGER NOT NULL DEFAULT 0,
                feedback_id INTEGER,
                FOREIGN KEY (feedback_id)
                    REFERENCES feedbacks(id)
            );

            CREATE TABLE IF NOT EXISTS feedbacks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_code TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'collecting',
                urgency TEXT,
                ticket_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_messages_customer
                ON messages(customer_code);

            CREATE INDEX IF NOT EXISTS idx_feedbacks_customer
                ON feedbacks(customer_code);

            CREATE INDEX IF NOT EXISTS idx_feedbacks_status
                ON feedbacks(status);
            """
        )


def save_message(
    customer_code: str,
    message_text: str,
    category: str,
    should_send_template: bool,
    group_code: str = "",
    sender: str = "",
    feedback_id: int | None = None,
) -> int:
    """保存一条客户群消息，返回数据库消息 ID。"""
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO messages (
                customer_code, group_code, sender, message_text,
                received_at, category, should_send_template, feedback_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_code,
                group_code,
                sender,
                message_text,
                now,
                category,
                int(should_send_template),
                feedback_id,
            ),
        )
        return cursor.lastrowid


def create_feedback(
    customer_code: str,
    category: str,
    description: str,
    title: str = "",
    urgency: str = "",
    ticket_id: str = "",
) -> int:
    """创建需求或 Bug 反馈记录，返回反馈 ID。"""
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO feedbacks (
                customer_code, category, title, description,
                status, urgency, ticket_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'collecting', ?, ?, ?, ?)
            """,
            (
                customer_code,
                category,
                title,
                description,
                urgency,
                ticket_id,
                now,
                now,
            ),
        )
        return cursor.lastrowid


def get_messages(customer_code: str = "") -> list[dict]:
    """读取消息；传入客户代码时只读取该客户。"""
    with get_connection() as conn:
        if customer_code:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE customer_code = ?
                ORDER BY id
                """,
                (customer_code,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM messages ORDER BY id"
            ).fetchall()

        return [dict(row) for row in rows]


def get_feedbacks(customer_code: str = "") -> list[dict]:
    """读取反馈记录；传入客户代码时只读取该客户。"""
    with get_connection() as conn:
        if customer_code:
            rows = conn.execute(
                """
                SELECT * FROM feedbacks
                WHERE customer_code = ?
                ORDER BY id
                """,
                (customer_code,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM feedbacks ORDER BY id"
            ).fetchall()

        return [dict(row) for row in rows]


def append_feedback_information(
    feedback_id: int,
    additional_text: str,
) -> bool:
    """将后续补充信息追加到已有反馈，不重复写入相同内容。"""
    additional_text = additional_text.strip()

    if not additional_text:
        return False

    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT description
            FROM feedbacks
            WHERE id = ?
            """,
            (feedback_id,),
        ).fetchone()

        if row is None:
            return False

        current_description = row["description"] or ""

        # 完全相同的补充内容不重复追加
        if additional_text in current_description:
            return False

        updated_description = (
            current_description
            + "\n\n【后续补充】\n"
            + additional_text
        )

        conn.execute(
            """
            UPDATE feedbacks
            SET description = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (updated_description, now, feedback_id),
        )

        return True

def run_demo():
    """初始化数据库，并验证消息与反馈可以写入、读取。"""
    init_db()

    message_id = save_message(
        customer_code="DEMO_A",
        group_code="DEMO_GROUP_A",
        sender="模拟客户A",
        message_text="素材下载功能报错，无法下载",
        category="bug",
        should_send_template=True,
    )

    feedback_id = create_feedback(
        customer_code="DEMO_A",
        category="bug",
        title="素材下载异常",
        description="素材下载功能报错，无法下载",
        urgency="待确认",
    )

    print("数据库初始化成功")
    print(f"数据库位置：{DB_PATH}")
    print(f"本次新增消息 ID：{message_id}")
    print(f"本次新增反馈 ID：{feedback_id}")
    print(f"消息读取结果：{len(get_messages('DEMO_A'))} 条")
    print(f"反馈读取结果：{len(get_feedbacks('DEMO_A'))} 条")


if __name__ == "__main__":
    run_demo()
