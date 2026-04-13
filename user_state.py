import json
import logging
import sqlite3
import zoneinfo
from pathlib import Path

from config import cfg

log = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent / "user_state.db"
_initialized = False


def _get_conn() -> sqlite3.Connection:
    global _initialized
    conn = sqlite3.connect(_DB_PATH)
    if not _initialized:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                tool_calls TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_history_user ON conversation_history(user_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id  TEXT PRIMARY KEY,
                timezone TEXT NOT NULL DEFAULT 'Asia/Manila'
            )
            """
        )
        conn.commit()
        _initialized = True
    return conn


def save_message(
    user_id: str,
    role: str,
    content: str,
    tool_calls: list | None = None,
) -> None:
    """Persist a single message to the conversation history."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO conversation_history (user_id, role, content, tool_calls) VALUES (?, ?, ?, ?)",
            (user_id, role, content, json.dumps(tool_calls) if tool_calls else None),
        )
        conn.commit()
        _trim_history(conn, user_id)
    finally:
        conn.close()


def get_history(user_id: str, limit: int = 0) -> list[dict]:
    """Return recent conversation messages for a user.

    Each dict has keys: role, content, tool_calls (optional).
    Ordered oldest-first.
    """
    if limit <= 0:
        limit = cfg.max_history_messages
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT role, content, tool_calls FROM (
                SELECT role, content, tool_calls, id
                FROM conversation_history
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) sub ORDER BY id ASC
            """,
            (user_id, limit),
        ).fetchall()
        result = []
        for role, content, tc_json in rows:
            msg: dict = {"role": role, "content": content}
            if tc_json:
                msg["tool_calls"] = json.loads(tc_json)
            result.append(msg)
        return result
    finally:
        conn.close()


def clear_history(user_id: str) -> None:
    """Delete all conversation history for a user."""
    conn = _get_conn()
    try:
        conn.execute(
            "DELETE FROM conversation_history WHERE user_id = ?", (user_id,)
        )
        conn.commit()
        log.info("Cleared history for user %s", user_id)
    finally:
        conn.close()


def _trim_history(conn: sqlite3.Connection, user_id: str) -> None:
    """Keep only the most recent messages per user."""
    conn.execute(
        """
        DELETE FROM conversation_history
        WHERE user_id = ? AND id NOT IN (
            SELECT id FROM conversation_history
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        )
        """,
        (user_id, user_id, cfg.max_history_messages),
    )
    conn.commit()


def get_timezone(user_id: str) -> str:
    """Return the user's configured timezone name, defaulting to Asia/Manila."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT timezone FROM user_preferences WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row[0] if row else cfg.default_timezone
    finally:
        conn.close()


def set_timezone(user_id: str, tz_name: str) -> str:
    """Set the user's timezone. Returns an error message if the tz name is invalid."""
    try:
        zoneinfo.ZoneInfo(tz_name)
    except KeyError:
        return f"Unknown timezone '{tz_name}'. Use an IANA name like 'Asia/Manila' or 'America/New_York'."

    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO user_preferences (user_id, timezone) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET timezone = excluded.timezone
            """,
            (user_id, tz_name),
        )
        conn.commit()
        log.info("Set timezone for user %s to %s", user_id, tz_name)
        return ""
    finally:
        conn.close()
