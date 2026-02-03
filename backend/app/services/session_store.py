import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from app.core.config import settings


def _get_db_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    db_path = Path(settings.case_db_path)
    if not db_path.is_absolute():
        db_path = root / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _get_conn() -> sqlite3.Connection:
    return sqlite3.connect(_get_db_path())


def ensure_case_sessions_table() -> None:
    with closing(_get_conn()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS case_sessions (
                session_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()


def get_session(session_id: str) -> dict[str, Any] | None:
    ensure_case_sessions_table()
    with closing(_get_conn()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT state_json FROM case_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    try:
        state = json.loads(str(row["state_json"]))
    except json.JSONDecodeError:
        return None
    return state if isinstance(state, dict) else None


def save_session(session_id: str, case_id: str, state: dict[str, Any]) -> None:
    ensure_case_sessions_table()
    payload = json.dumps(state, ensure_ascii=False)
    with closing(_get_conn()) as conn:
        conn.execute(
            """
            INSERT INTO case_sessions (session_id, case_id, state_json, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(session_id)
            DO UPDATE SET
                case_id = excluded.case_id,
                state_json = excluded.state_json,
                updated_at = datetime('now')
            """,
            (session_id, case_id, payload),
        )
        conn.commit()


def delete_session(session_id: str) -> None:
    ensure_case_sessions_table()
    with closing(_get_conn()) as conn:
        conn.execute("DELETE FROM case_sessions WHERE session_id = ?", (session_id,))
        conn.commit()
