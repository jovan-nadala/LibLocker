"""Database connection and initialization utilities."""

import logging
from pathlib import Path
import sqlite3

import click
from flask import current_app, g

MAX_LOCKER_COUNT = 24
logger = logging.getLogger(__name__)


def _active_locker_count() -> int:
    """Return the configured locker count, clamped to the supported range."""
    configured = current_app.config.get("ACTIVE_LOCKER_COUNT", MAX_LOCKER_COUNT)
    try:
        parsed = int(configured)
    except (TypeError, ValueError):
        parsed = MAX_LOCKER_COUNT
    return max(1, min(parsed, MAX_LOCKER_COUNT))


def _split_range(start: int, end: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Split an inclusive range into two contiguous halves."""
    if start > end:
        return (start, end), (start, end)
    midpoint = start + ((end - start) // 2)
    return (start, midpoint), (midpoint + 1, end)


def _locker_group_for_number(locker_number: int, active_count: int) -> str:
    """Assign a quarter-style group name for the active locker count."""
    upper = (1, (active_count + 1) // 2)
    lower = (upper[1] + 1, active_count)
    upper1, upper2 = _split_range(*upper)
    lower1, lower2 = _split_range(*lower)

    if upper1[0] <= locker_number <= upper1[1]:
        return "upper1"
    if upper2[0] <= locker_number <= upper2[1]:
        return "upper2"
    if lower1[0] <= locker_number <= lower1[1]:
        return "lower1"
    return "lower2"


def _locker_level_for_number(locker_number: int, active_count: int) -> int:
    """Map lockers into upper/lower levels for the active locker count."""
    return 1 if locker_number <= ((active_count + 1) // 2) else 2


def _create_base_tables(db: sqlite3.Connection) -> None:
    """Create baseline tables without relying on post-migration columns."""
    db.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          full_name TEXT NOT NULL,
          student_id TEXT NOT NULL UNIQUE,
          rfid_uid TEXT UNIQUE,
          created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          locker_id INTEGER NOT NULL,
          action TEXT NOT NULL CHECK(action IN ('deposit', 'retrieve')),
          status TEXT NOT NULL DEFAULT 'active'
            CHECK(status IN ('active', 'completed', 'canceled')),
          access_code TEXT,
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          completed_at TEXT,
          evidence_photo TEXT,
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY (locker_id) REFERENCES lockers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS lockers (
          id INTEGER PRIMARY KEY,
          label TEXT NOT NULL UNIQUE,
          level INTEGER,
          status TEXT NOT NULL CHECK (status IN ('available', 'occupied', 'maintenance')) DEFAULT 'available',
          updated_at TEXT NOT NULL DEFAULT (datetime('now')),
          current_user_id INTEGER,
          current_session_id INTEGER,
          current_rfid_uid TEXT,
          locker_number INTEGER UNIQUE CHECK (locker_number BETWEEN 1 AND 24),
          locker_group TEXT CHECK (locker_group IN ('upper1', 'upper2', 'lower1', 'lower2')),
          is_occupied INTEGER NOT NULL DEFAULT 0 CHECK (is_occupied IN (0, 1)),
          last_opened_at TEXT,
          FOREIGN KEY (current_user_id) REFERENCES users(id) ON DELETE SET NULL ON UPDATE CASCADE,
          FOREIGN KEY (current_session_id) REFERENCES sessions(id) ON DELETE SET NULL ON UPDATE CASCADE
        );

        CREATE TABLE IF NOT EXISTS activity_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          timestamp TEXT NOT NULL DEFAULT (datetime('now')),
          activity_type TEXT NOT NULL,
          locker_id INTEGER,
          user_id INTEGER,
          details TEXT,
          status TEXT NOT NULL DEFAULT 'success' CHECK(status IN ('success', 'warning', 'error')),
          FOREIGN KEY (locker_id) REFERENCES lockers(id) ON DELETE SET NULL,
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS transactions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          locker_id INTEGER NOT NULL,
          action TEXT NOT NULL CHECK(action IN ('DEPOSIT', 'RETRIEVE')),
          status TEXT NOT NULL DEFAULT 'DONE' CHECK(status IN ('DONE', 'FAILED')),
          created_at TEXT NOT NULL DEFAULT (datetime('now')),
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY (locker_id) REFERENCES lockers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          level TEXT NOT NULL DEFAULT 'INFO' CHECK(level IN ('DEBUG', 'INFO', 'WARN', 'ERROR')),
          message TEXT NOT NULL,
          meta_json TEXT,
          created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )


def get_db() -> sqlite3.Connection:
    """Get a request-scoped SQLite connection."""
    if "db" not in g:
        db_path = Path(current_app.config["DATABASE_PATH"])
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
        except sqlite3.OperationalError:
            logger.warning("SQLite WAL mode unavailable for %s; falling back to default journal mode.", db_path)
        g.db = conn

    return g.db


def close_db(exception: Exception | None = None) -> None:
    """Close request-scoped database connection."""
    _ = exception
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """Initialize and migrate schema from schema.sql."""
    db = get_db()
    _create_base_tables(db)
    _migrate_schema(db)
    _seed_lockers(db)
    db.commit()


def _table_exists(db: sqlite3.Connection, table_name: str) -> bool:
    """Return True when table exists in current database."""
    row = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _ensure_columns(
    db: sqlite3.Connection,
    table_name: str,
    required_columns: dict[str, str],
) -> None:
    """Add missing columns on an existing table."""
    if not _table_exists(db, table_name):
        return

    columns = db.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing = {row["name"] for row in columns}

    for column_name, column_sql in required_columns.items():
        if column_name in existing:
            continue
        db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")


def _column_not_null(db: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    """Return True when a specific column is defined as NOT NULL."""
    if not _table_exists(db, table_name):
        return False

    columns = db.execute(f"PRAGMA table_info({table_name})").fetchall()
    for column in columns:
        if column["name"] == column_name:
            return bool(column["notnull"])
    return False


def _migrate_users_table(db: sqlite3.Connection) -> None:
    """Ensure users table supports pending registration with nullable RFID."""
    if not _table_exists(db, "users"):
        return

    # Legacy schema had rfid_uid NOT NULL, which blocks details-first registration.
    if not _column_not_null(db, "users", "rfid_uid"):
        return

    db.execute("PRAGMA foreign_keys = OFF")
    try:
        db.execute("DROP TABLE IF EXISTS users_new")
        db.execute(
            """
            CREATE TABLE users_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              full_name TEXT NOT NULL,
              student_id TEXT NOT NULL UNIQUE,
              rfid_uid TEXT UNIQUE,
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        db.execute(
            """
            INSERT INTO users_new(id, full_name, student_id, rfid_uid, created_at)
            SELECT
                id,
                COALESCE(NULLIF(TRIM(full_name), ''), 'Unknown User'),
                student_id,
                CASE
                    WHEN TRIM(COALESCE(rfid_uid, '')) = '' THEN NULL
                    ELSE rfid_uid
                END,
                COALESCE(created_at, datetime('now'))
            FROM users
            """
        )
        db.execute("DROP TABLE users")
        db.execute("ALTER TABLE users_new RENAME TO users")
    finally:
        db.execute("PRAGMA foreign_keys = ON")


def _table_references(db: sqlite3.Connection, table_name: str, target_table: str) -> bool:
    """Return True when table has any FK that references target_table."""
    if not _table_exists(db, table_name):
        return False
    refs = db.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
    return any(ref["table"] == target_table for ref in refs)


def _repair_user_foreign_keys(db: sqlite3.Connection) -> None:
    """Repair broken FK references that point to users_legacy."""
    legacy_targets = {"users_legacy", "sessions_legacy_fk", "lockers_legacy_fk"}
    has_legacy_fk = False
    for table_name in ("lockers", "sessions", "activity_logs", "transactions"):
        if not _table_exists(db, table_name):
            continue
        refs = db.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
        if any(ref["table"] in legacy_targets for ref in refs):
            has_legacy_fk = True
            break

    if not has_legacy_fk and not any(
        _table_exists(db, table_name)
        for table_name in (
            "users_legacy",
            "lockers_legacy_fk",
            "sessions_legacy_fk",
            "activity_logs_legacy_fk",
            "transactions_legacy_fk",
        )
    ):
        return

    db.execute("PRAGMA foreign_keys = OFF")
    try:
        if _table_exists(db, "lockers"):
            db.execute("DROP TABLE IF EXISTS lockers_new")
            db.execute(
                """
                CREATE TABLE lockers_new (
                  id INTEGER PRIMARY KEY,
                  label TEXT NOT NULL UNIQUE,
                  level INTEGER,
                  status TEXT NOT NULL CHECK (status IN ('available', 'occupied', 'maintenance')) DEFAULT 'available',
                  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                  current_user_id INTEGER,
                  current_session_id INTEGER,
                  locker_number INTEGER UNIQUE CHECK (locker_number BETWEEN 1 AND 24),
                  locker_group TEXT CHECK (locker_group IN ('upper1', 'upper2', 'lower1', 'lower2')),
                  is_occupied INTEGER NOT NULL DEFAULT 0 CHECK (is_occupied IN (0, 1)),
                  last_opened_at TEXT,
                  FOREIGN KEY (current_user_id) REFERENCES users(id) ON DELETE SET NULL ON UPDATE CASCADE,
                  FOREIGN KEY (current_session_id) REFERENCES sessions(id) ON DELETE SET NULL ON UPDATE CASCADE
                )
                """
            )
            db.execute(
                """
                INSERT INTO lockers_new(
                    id, label, level, status, updated_at,
                    current_user_id, current_session_id, locker_number,
                    locker_group, is_occupied, last_opened_at
                )
                SELECT
                    id, label, level, status, updated_at,
                    current_user_id, current_session_id, locker_number,
                    locker_group, is_occupied, last_opened_at
                FROM lockers
                """
            )

        if _table_exists(db, "sessions"):
            db.execute("DROP TABLE IF EXISTS sessions_new")
            db.execute(
                """
                CREATE TABLE sessions_new (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  locker_id INTEGER NOT NULL,
                  action TEXT NOT NULL CHECK(action IN ('deposit', 'retrieve')),
                  status TEXT NOT NULL DEFAULT 'active'
                    CHECK(status IN ('active', 'completed', 'canceled')),
                  access_code TEXT,
                  created_at TEXT NOT NULL DEFAULT (datetime('now')),
                  completed_at TEXT,
                  evidence_photo TEXT,
                  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                  FOREIGN KEY (locker_id) REFERENCES lockers(id) ON DELETE CASCADE
                )
                """
            )
            db.execute(
                """
                INSERT INTO sessions_new(
                    id, user_id, locker_id, action, status,
                    access_code, created_at, completed_at
                )
                SELECT
                    id, user_id, locker_id, action, status,
                    access_code, created_at, completed_at
                FROM sessions
                """
            )

        if _table_exists(db, "activity_logs"):
            db.execute("DROP TABLE IF EXISTS activity_logs_new")
            db.execute(
                """
                CREATE TABLE activity_logs_new (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                  activity_type TEXT NOT NULL,
                  locker_id INTEGER,
                  user_id INTEGER,
                  details TEXT,
                  status TEXT NOT NULL DEFAULT 'success' CHECK(status IN ('success', 'warning', 'error')),
                  FOREIGN KEY (locker_id) REFERENCES lockers(id) ON DELETE SET NULL,
                  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
                )
                """
            )
            db.execute(
                """
                INSERT INTO activity_logs_new(
                    id, timestamp, activity_type, locker_id,
                    user_id, details, status
                )
                SELECT
                    id, timestamp, activity_type, locker_id,
                    user_id, details, status
                FROM activity_logs
                """
            )

        if _table_exists(db, "transactions"):
            db.execute("DROP TABLE IF EXISTS transactions_new")
            db.execute(
                """
                CREATE TABLE transactions_new (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER NOT NULL,
                  locker_id INTEGER NOT NULL,
                  action TEXT NOT NULL CHECK(action IN ('DEPOSIT', 'RETRIEVE')),
                  status TEXT NOT NULL DEFAULT 'DONE' CHECK(status IN ('DONE', 'FAILED')),
                  created_at TEXT NOT NULL DEFAULT (datetime('now')),
                  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                  FOREIGN KEY (locker_id) REFERENCES lockers(id) ON DELETE CASCADE
                )
                """
            )
            db.execute(
                """
                INSERT INTO transactions_new(
                    id, user_id, locker_id, action, status, created_at
                )
                SELECT
                    id, user_id, locker_id, action, status, created_at
                FROM transactions
                """
            )

        for table_name in ("activity_logs", "transactions", "sessions", "lockers"):
            if _table_exists(db, table_name):
                db.execute(f"DROP TABLE {table_name}")

        rename_pairs = (
            ("lockers_new", "lockers"),
            ("sessions_new", "sessions"),
            ("activity_logs_new", "activity_logs"),
            ("transactions_new", "transactions"),
        )
        for src, dst in rename_pairs:
            if _table_exists(db, src):
                db.execute(f"ALTER TABLE {src} RENAME TO {dst}")

        for table_name in (
            "users_legacy",
            "lockers_legacy_fk",
            "sessions_legacy_fk",
            "activity_logs_legacy_fk",
            "transactions_legacy_fk",
        ):
            if _table_exists(db, table_name):
                db.execute(f"DROP TABLE {table_name}")
    finally:
        db.execute("PRAGMA foreign_keys = ON")


def _migrate_schema(db: sqlite3.Connection) -> None:
    """Migrate legacy database layouts into the current schema."""
    _ensure_columns(
        db,
        "lockers",
        {
            "locker_number": "locker_number INTEGER",
            "locker_group": "locker_group TEXT",
            "is_occupied": "is_occupied INTEGER NOT NULL DEFAULT 0",
            "last_opened_at": "last_opened_at TEXT",
            "label": "label TEXT",
            "level": "level INTEGER",
            "status": "status TEXT NOT NULL DEFAULT 'available'",
            "updated_at": "updated_at TEXT",
            "current_user_id": "current_user_id INTEGER",
            "current_session_id": "current_session_id INTEGER",
            "current_rfid_uid": "current_rfid_uid TEXT",
        },
    )
    _ensure_columns(
        db,
        "users",
        {
            "created_at": "created_at TEXT NOT NULL DEFAULT (datetime('now'))",
            "rfid_uid": "rfid_uid TEXT",
        },
    )
    _ensure_columns(
        db,
        "sessions",
        {
            "evidence_photo": "evidence_photo TEXT",
        },
    )
    _migrate_users_table(db)
    _repair_user_foreign_keys(db)
    _ensure_columns(
        db,
        "activity_logs",
        {
            "status": "status TEXT NOT NULL DEFAULT 'success'",
            "details": "details TEXT",
        },
    )

    if _table_exists(db, "lockers"):
        db.execute("UPDATE lockers SET locker_number = COALESCE(locker_number, id)")
        db.execute(
            """
            UPDATE lockers
            SET locker_group = CASE
                WHEN locker_group IN ('upper1', 'upper2', 'lower1', 'lower2') THEN locker_group
                WHEN COALESCE(locker_number, id) BETWEEN 1 AND 6 THEN 'upper1'
                WHEN COALESCE(locker_number, id) BETWEEN 7 AND 12 THEN 'upper2'
                WHEN COALESCE(locker_number, id) BETWEEN 13 AND 18 THEN 'lower1'
                WHEN COALESCE(locker_number, id) BETWEEN 19 AND 24 THEN 'lower2'
                ELSE 'upper1'
            END
            """
        )
        db.execute(
            """
            UPDATE lockers
            SET status = CASE
                WHEN status IN ('available', 'occupied', 'maintenance') THEN status
                WHEN is_occupied = 1 THEN 'occupied'
                ELSE 'available'
            END
            """
        )
        db.execute(
            "UPDATE lockers SET is_occupied = CASE WHEN status = 'occupied' THEN 1 ELSE 0 END"
        )
        db.execute(
            "UPDATE lockers SET label = COALESCE(NULLIF(label, ''), CAST(COALESCE(locker_number, id) AS TEXT))"
        )
        db.execute(
            "UPDATE lockers SET level = COALESCE(level, ((COALESCE(locker_number, id) - 1) / 6) + 1)"
        )
        db.execute("UPDATE lockers SET updated_at = COALESCE(updated_at, datetime('now'))")

    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_lockers_label ON lockers(label)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_lockers_number ON lockers(locker_number)"
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_lockers_one_active_per_user
        ON lockers(current_user_id)
        WHERE current_user_id IS NOT NULL AND is_occupied = 1
        """
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_student_id ON users(student_id)"
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_rfid_uid ON users(rfid_uid)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_logs_timestamp ON activity_logs(timestamp)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_activity_logs_type ON activity_logs(activity_type)"
    )


def _seed_lockers(db: sqlite3.Connection) -> None:
    """Ensure supported lockers exist and active lockers use current grouping."""
    active_count = _active_locker_count()
    db.execute(
        """
        WITH RECURSIVE locker_ids(n) AS (
            SELECT 1
            UNION ALL
            SELECT n + 1 FROM locker_ids WHERE n < 24
        )
        INSERT OR IGNORE INTO lockers (
            id,
            locker_number,
            label,
            level,
            locker_group,
            status,
            is_occupied,
            updated_at
        )
        SELECT
            n,
            n,
            CAST(n AS TEXT),
            ((n - 1) / 6) + 1,
            CASE
                WHEN n BETWEEN 1 AND 6   THEN 'upper1'
                WHEN n BETWEEN 7 AND 12  THEN 'upper2'
                WHEN n BETWEEN 13 AND 18 THEN 'lower1'
                ELSE                          'lower2'
            END,
            'available',
            0,
            datetime('now')
        FROM locker_ids
        """
    )
    db.execute(
        """
        UPDATE lockers
        SET label = COALESCE(NULLIF(label, ''), CAST(COALESCE(locker_number, id) AS TEXT)),
            level = COALESCE(level, ((COALESCE(locker_number, id) - 1) / 6) + 1),
            updated_at = COALESCE(updated_at, datetime('now'))
        WHERE COALESCE(locker_number, id) BETWEEN 1 AND 24
        """
    )

    for locker_number in range(1, active_count + 1):
        db.execute(
            """
            UPDATE lockers
            SET locker_group = ?,
                level = ?,
                updated_at = datetime('now')
            WHERE COALESCE(locker_number, id) = ?
            """,
            (
                _locker_group_for_number(locker_number, active_count),
                _locker_level_for_number(locker_number, active_count),
                locker_number,
            ),
        )


@click.command("init-db")
def init_db_command() -> None:
    """CLI command to initialize the database."""
    init_db()
    click.echo("Database initialized.")


def register_db(app) -> None:
    """Register DB hooks and CLI commands with the Flask app."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
