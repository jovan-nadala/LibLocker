"""Audit logging service."""

import json
from typing import Any

from app.db import get_db


def log_audit_event(message: str, level: str = "INFO", meta: dict[str, Any] | None = None) -> None:
    """Insert a structured audit log record."""
    db = get_db()
    payload = json.dumps(meta, ensure_ascii=True) if meta else None
    db.execute(
        "INSERT INTO audit_logs(level, message, meta_json) VALUES(?,?,?)",
        (level, message, payload),
    )
    db.commit()


def list_recent_logs(limit: int = 200) -> list[dict[str, Any]]:
    """Return latest audit logs."""
    max_rows = max(1, min(int(limit), 200))
    db = get_db()
    rows = db.execute(
        """
        SELECT id, level, message, meta_json, created_at
        FROM audit_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (max_rows,),
    ).fetchall()
    return [dict(row) for row in rows]
