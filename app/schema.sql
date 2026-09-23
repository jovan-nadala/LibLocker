PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  full_name TEXT NOT NULL,
  student_id TEXT NOT NULL UNIQUE,
  rfid_uid TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
  FOREIGN KEY (current_user_id) REFERENCES users(id) ON DELETE SET NULL
    ON UPDATE CASCADE,
  FOREIGN KEY (current_session_id) REFERENCES sessions(id) ON DELETE SET NULL
    ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  locker_id INTEGER NOT NULL,
  action TEXT NOT NULL CHECK(action IN ('deposit', 'retrieve')),
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed', 'canceled')),
  access_code TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  completed_at TEXT,
  evidence_photo TEXT,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (locker_id) REFERENCES lockers(id) ON DELETE CASCADE
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_lockers_one_active_per_user
ON lockers(current_user_id)
WHERE current_user_id IS NOT NULL AND is_occupied = 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_lockers_label ON lockers(label);
CREATE UNIQUE INDEX IF NOT EXISTS idx_lockers_number ON lockers(locker_number);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_rfid_uid ON users(rfid_uid) WHERE rfid_uid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_activity_logs_timestamp ON activity_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_activity_logs_type ON activity_logs(activity_type);

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

WITH RECURSIVE locker_ids(n) AS (
  SELECT 1
  UNION ALL
  SELECT n + 1 FROM locker_ids WHERE n < 24
)
INSERT OR IGNORE INTO lockers (
  id,
  label,
  level,
  status,
  updated_at,
  locker_number,
  locker_group,
  is_occupied
)
SELECT
  n,
  printf('L-%02d', n),
  ((n - 1) / 6) + 1,
  'available',
  datetime('now'),
  n,
  CASE
    WHEN n BETWEEN 1 AND 6 THEN 'upper1'
    WHEN n BETWEEN 7 AND 12 THEN 'upper2'
    WHEN n BETWEEN 13 AND 18 THEN 'lower1'
    ELSE 'lower2'
  END,
  0
FROM locker_ids;