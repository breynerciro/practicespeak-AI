"""Persistencia ligera en SQLite: sesiones de práctica, correcciones y stats.

Usa la stdlib (sqlite3, sin ORM) para cero dependencias extra. El hilo de
Whisper y los endpoints async comparten una conexión por proceso con
check_same_thread=False + un lock, suficiente para uso personal.
"""
import sqlite3
import threading
import time
from pathlib import Path

from . import config

DB_PATH = Path(config.LOG_DIR).parent / "nova.db"
_conn: sqlite3.Connection | None = None
_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    finished_at REAL,
    language TEXT NOT NULL,
    topic TEXT,
    mode TEXT NOT NULL DEFAULT 'voice',
    profile_id INTEGER REFERENCES profiles(id)
);

CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    created_at REAL NOT NULL,
    language TEXT NOT NULL,
    topic TEXT,
    user_text TEXT NOT NULL,
    error TEXT NOT NULL,
    correction TEXT NOT NULL,
    explanation TEXT
);
"""


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(_SCHEMA)
        _migrate(_conn)
        _conn.commit()
    return _conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Migraciones incrementales para bases ya creadas (PRAGMA de columnas)."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
    if "profile_id" not in cols:
        conn.execute("ALTER TABLE sessions ADD COLUMN profile_id INTEGER REFERENCES profiles(id)")


def _normalize_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("El nombre no puede estar vacío")
    if len(name) > 40:
        raise ValueError("El nombre es demasiado largo (máximo 40 caracteres)")
    return name


def list_profiles() -> list[dict]:
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT p.id, p.name, p.created_at,"
            " (SELECT COUNT(*) FROM sessions s WHERE s.profile_id = p.id) AS sessions"
            " FROM profiles p ORDER BY p.name COLLATE NOCASE, p.id"
        ).fetchall()
    return [dict(r) for r in rows]


def create_profile(name: str) -> int:
    with _lock:
        conn = _get_conn()
        cur = conn.execute(
            "INSERT INTO profiles (name, created_at) VALUES (?, ?)",
            (_normalize_name(name), time.time()),
        )
        return int(cur.lastrowid or 0)


def start_session(language: str, topic: str | None, mode: str, profile_id: int | None = None) -> int:
    with _lock, _get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (started_at, language, topic, mode, profile_id) VALUES (?, ?, ?, ?, ?)",
            (time.time(), language, topic, mode, profile_id),
        )
        return int(cur.lastrowid or 0)


def save_corrections(session_id: int, language: str, topic: str | None, user_text: str, corrections: list[dict]) -> int:
    if not corrections:
        return 0
    now = time.time()
    with _lock, _get_conn() as conn:
        conn.executemany(
            "INSERT INTO corrections (session_id, created_at, language, topic, user_text, error, correction, explanation)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    session_id,
                    now,
                    language,
                    topic,
                    user_text[:500],
                    str(c.get("error", ""))[:300],
                    str(c.get("correction", ""))[:300],
                    str(c.get("explanation", ""))[:500],
                )
                for c in corrections
            ],
        )
    return len(corrections)


def finish_session(session_id: int) -> None:
    with _lock, _get_conn() as conn:
        conn.execute("UPDATE sessions SET finished_at = ? WHERE id = ?", (time.time(), session_id))


def _correction_filter(profile_id: int | None) -> tuple[str, tuple]:
    """SQL + params para filtrar correcciones por perfil (JOIN con sesiones)."""
    if profile_id is None:
        return "", ()
    return " JOIN sessions s ON s.id = corrections.session_id AND s.profile_id = ?", (profile_id,)


def stats(profile_id: int | None = None) -> dict:
    with _lock:
        conn = _get_conn()
        one_week = time.time() - 7 * 86400
        session_filter = " WHERE profile_id == ?" if profile_id is not None else ""
        session_params = (profile_id,) if profile_id is not None else ()

        totals = conn.execute("SELECT COUNT(*) AS sessions FROM sessions" + session_filter, session_params).fetchone()
        week = conn.execute(
            "SELECT COUNT(*) AS sessions FROM sessions"
            + (session_filter if profile_id is not None else " WHERE started_at >= ?")
            + (" AND started_at >= ?" if profile_id is not None else ""),
            session_params + (one_week,),
        ).fetchone()

        corr_sql, corr_params = _correction_filter(profile_id)
        corr = conn.execute(
            "SELECT COUNT(*) AS n FROM corrections" + corr_sql, corr_params
        ).fetchone()
        by_lang = conn.execute(
            "SELECT language, COUNT(*) AS n FROM sessions" + session_filter + " GROUP BY language ORDER BY n DESC",
            session_params,
        ).fetchall()
        by_topic = conn.execute(
            "SELECT corrections.topic AS topic, COUNT(*) AS n FROM corrections" + corr_sql
            + (" AND" if corr_sql else " WHERE") + " corrections.topic IS NOT NULL"
            + " GROUP BY corrections.topic ORDER BY n DESC LIMIT 10",
            corr_params,
        ).fetchall()
    return {
        "total_sessions": totals["sessions"],
        "sessions_last_7d": week["sessions"],
        "total_corrections": corr["n"],
        "by_language": {r["language"]: r["n"] for r in by_lang},
        "top_topics_with_errors": {r["topic"]: r["n"] for r in by_topic},
    }


def export_anki_csv(profile_id: int | None = None) -> str:
    """CSV compatible con Anki: Front=error, Back=corrección + regla."""
    import csv
    import io

    with _lock:
        conn = _get_conn()
        corr_sql, corr_params = _correction_filter(profile_id)
        rows = conn.execute(
            "SELECT error, correction, explanation FROM corrections" + corr_sql
            + " ORDER BY created_at DESC",
            corr_params,
        ).fetchall()
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
    writer.writerow(["Front", "Back"])
    for row in rows:
        back = row["correction"] + (f"<br><br><i>{row['explanation']}</i>" if row["explanation"] else "")
        writer.writerow([row["error"], back])
    return buf.getvalue()


def reset_for_tests(db_path: Path) -> None:
    """Solo para tests: apunta a otra base y resetea la conexión."""
    global _conn, DB_PATH
    DB_PATH = db_path
    if _conn is not None:
        _conn.close()
    _conn = None
    _get_conn()
