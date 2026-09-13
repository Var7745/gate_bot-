"""
SQLite Database Engine for GATE 2027 Study Companion (v3 Production)
Features:
1. Active Telegram polls with topic & module metadata
2. Practice questions table with deterministic answer verification
3. Deduplicated quiz attempts for both PYQs and AI practice
4. Granular topic-level weak area tracking
5. Restart-safe scheduler state (last_dispatched_date)
6. Persistent multi-turn chat history
"""

import os
import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DB_FILE = DATA_DIR / "gate_companion.db"


def get_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=15.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS active_polls (
                poll_id TEXT PRIMARY KEY,
                subject_code TEXT NOT NULL,
                module_id TEXT,
                topic_name TEXT,
                correct_id INTEGER NOT NULL,
                question TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS practice_questions (
                question_id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                subject_code TEXT NOT NULL,
                module_id TEXT,
                topic_name TEXT NOT NULL,
                question TEXT NOT NULL,
                options_json TEXT NOT NULL,
                correct_id INTEGER NOT NULL,
                explanation TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                subject_code TEXT NOT NULL,
                module_id TEXT,
                topic_name TEXT,
                question_source TEXT NOT NULL,
                chosen_id INTEGER NOT NULL,
                is_correct BOOLEAN NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(question_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS weak_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_code TEXT NOT NULL,
                module_id TEXT,
                topic_name TEXT NOT NULL,
                error_count INTEGER DEFAULT 1,
                last_mistake_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(subject_code, module_id, topic_name)
            );

            CREATE TABLE IF NOT EXISTS scheduler_state (
                key TEXT PRIMARY KEY,
                val TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Automatic schema migration for existing databases
        def _add_col(t, col, ctype):
            try:
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
                if col not in cols:
                    conn.execute(f"ALTER TABLE {t} ADD COLUMN {col} {ctype}")
            except Exception:
                pass

        _add_col("active_polls", "module_id", "TEXT")
        _add_col("active_polls", "topic_name", "TEXT")
        _add_col("quiz_attempts", "module_id", "TEXT")
        _add_col("quiz_attempts", "topic_name", "TEXT")
        _add_col("quiz_attempts", "question_source", "TEXT DEFAULT 'gate_pyq'")
        _add_col("weak_topics", "module_id", "TEXT")


def save_active_poll(poll_id, subject_code, correct_id, question="", module_id="NET-M01", topic_name="General"):
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO active_polls 
               (poll_id, subject_code, module_id, topic_name, correct_id, question) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (str(poll_id), str(subject_code), str(module_id), str(topic_name), int(correct_id), str(question))
        )


def get_active_poll(poll_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM active_polls WHERE poll_id = ?", (str(poll_id),)).fetchone()
        return dict(row) if row else None


def record_poll_attempt(poll_id, user_id, chosen_id):
    meta = get_active_poll(poll_id)
    if not meta:
        return None, None, None  # Ignore unknown or expired polls cleanly

    subject_code = meta.get("subject_code", "NET")
    module_id = meta.get("module_id", "NET-M01")
    topic_name = meta.get("topic_name", "General Concepts")
    is_correct = (int(chosen_id) == meta.get("correct_id"))

    with get_db() as conn:
        # Check if already attempted by this user to prevent duplicate scoring
        existing = conn.execute(
            "SELECT 1 FROM quiz_attempts WHERE question_id = ? AND user_id = ?",
            (str(poll_id), str(user_id))
        ).fetchone()
        if existing:
            return is_correct, subject_code, topic_name

        conn.execute(
            """INSERT INTO quiz_attempts (question_id, user_id, subject_code, module_id, topic_name, question_source, chosen_id, is_correct)
               VALUES (?, ?, ?, ?, ?, 'poll', ?, ?)""",
            (str(poll_id), str(user_id), str(subject_code), str(module_id), str(topic_name), int(chosen_id), bool(is_correct))
        )
        if not is_correct:
            conn.execute(
                """INSERT INTO weak_topics (subject_code, module_id, topic_name, error_count, last_mistake_at)
                   VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
                   ON CONFLICT(subject_code, module_id, topic_name) DO UPDATE SET
                   error_count = error_count + 1,
                   last_mistake_at = CURRENT_TIMESTAMP""",
                (str(subject_code), str(module_id), str(topic_name))
            )
    return is_correct, subject_code, topic_name


def save_practice_question(question_id, chat_id, subject_code, module_id, topic_name, question, options, correct_id, explanation):
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO practice_questions 
               (question_id, chat_id, subject_code, module_id, topic_name, question, options_json, correct_id, explanation)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(question_id), str(chat_id), str(subject_code), str(module_id), str(topic_name),
             str(question), json.dumps(options), int(correct_id), str(explanation))
        )


def get_practice_question(question_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM practice_questions WHERE question_id = ?", (str(question_id),)).fetchone()
        if row:
            d = dict(row)
            d["options"] = json.loads(d["options_json"])
            return d
        return None


def record_practice_attempt(question_id, user_id, chosen_id):
    pq = get_practice_question(question_id)
    if not pq:
        return None, None, None

    is_correct = (int(chosen_id) == pq["correct_id"])
    subject_code = pq["subject_code"]
    module_id = pq.get("module_id", "NET-M01")
    topic_name = pq["topic_name"]

    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM quiz_attempts WHERE question_id = ? AND user_id = ?",
            (str(question_id), str(user_id))
        ).fetchone()
        if not existing:
            conn.execute(
                """INSERT INTO quiz_attempts (question_id, user_id, subject_code, module_id, topic_name, question_source, chosen_id, is_correct)
                   VALUES (?, ?, ?, ?, ?, 'practice', ?, ?)""",
                (str(question_id), str(user_id), str(subject_code), str(module_id), str(topic_name), int(chosen_id), bool(is_correct))
            )
            if not is_correct:
                conn.execute(
                    """INSERT INTO weak_topics (subject_code, module_id, topic_name, error_count, last_mistake_at)
                       VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
                       ON CONFLICT(subject_code, module_id, topic_name) DO UPDATE SET
                       error_count = error_count + 1,
                       last_mistake_at = CURRENT_TIMESTAMP""",
                    (str(subject_code), str(module_id), str(topic_name))
                )
    return is_correct, pq, topic_name


def record_pyq_attempt(question_id, user_id, subject_code, module_id, topic_name, chosen_id, is_correct):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT 1 FROM quiz_attempts WHERE question_id = ? AND user_id = ?",
            (str(question_id), str(user_id))
        ).fetchone()
        if existing:
            return

        conn.execute(
            """INSERT INTO quiz_attempts (question_id, user_id, subject_code, module_id, topic_name, question_source, chosen_id, is_correct)
               VALUES (?, ?, ?, ?, ?, 'pyq', ?, ?)""",
            (str(question_id), str(user_id), str(subject_code), str(module_id), str(topic_name), int(chosen_id), bool(is_correct))
        )
        if not is_correct:
            conn.execute(
                """INSERT INTO weak_topics (subject_code, module_id, topic_name, error_count, last_mistake_at)
                   VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
                   ON CONFLICT(subject_code, module_id, topic_name) DO UPDATE SET
                   error_count = error_count + 1,
                   last_mistake_at = CURRENT_TIMESTAMP""",
                (str(subject_code), str(module_id), str(topic_name))
            )


def get_analytics_summary():
    with get_db() as conn:
        total_attempts = conn.execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0]
        correct_count = conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE is_correct = 1").fetchone()[0]

        subject_stats = {}
        rows = conn.execute("""
            SELECT subject_code,
                   COUNT(*) as attempted,
                   SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct
            FROM quiz_attempts
            GROUP BY subject_code
        """).fetchall()

        for r in rows:
            subject_stats[r["subject_code"]] = {
                "attempted": r["attempted"],
                "correct": r["correct"] or 0
            }

        weak_rows = conn.execute("""
            SELECT subject_code, module_id, topic_name, error_count 
            FROM weak_topics 
            ORDER BY error_count DESC 
            LIMIT 4
        """).fetchall()

        weak_topics = [
            f"• <b>{r['topic_name']}</b> ({r['module_id']}): <code>{r['error_count']} mistakes</code>"
            for r in weak_rows
        ]

        return {
            "total_attempts": total_attempts,
            "correct_count": correct_count,
            "accuracy_pct": (correct_count / total_attempts * 100) if total_attempts > 0 else 0.0,
            "by_subject": subject_stats,
            "weak_topics": weak_topics
        }


def get_last_dispatch_date():
    with get_db() as conn:
        row = conn.execute("SELECT val FROM scheduler_state WHERE key = 'last_dispatched_date'").fetchone()
        return row["val"] if row else None


def set_last_dispatch_date(date_str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO scheduler_state (key, val, updated_at) VALUES ('last_dispatched_date', ?, CURRENT_TIMESTAMP)",
            (str(date_str),)
        )


def add_chat_turn(user_id, role, content):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)",
            (str(user_id), str(role), str(content))
        )
        conn.execute("""
            DELETE FROM chat_history 
            WHERE id NOT IN (
                SELECT id FROM chat_history WHERE user_id = ? ORDER BY id DESC LIMIT 20
            ) AND user_id = ?
        """, (str(user_id), str(user_id)))


def get_chat_history_turns(user_id, limit=8):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM chat_history WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (str(user_id), int(limit))
        ).fetchall()
        return [{"role": r["role"], "parts": [{"text": r["content"]}]} for r in reversed(rows)]


def clear_chat_history(user_id):
    with get_db() as conn:
        conn.execute("DELETE FROM chat_history WHERE user_id = ?", (str(user_id),))


def get_latest_question():
    with get_db() as conn:
        row_poll = conn.execute("SELECT question, topic_name FROM active_polls ORDER BY created_at DESC LIMIT 1").fetchone()
        row_prac = conn.execute("SELECT question, topic_name FROM practice_questions ORDER BY created_at DESC LIMIT 1").fetchone()
        if row_poll and row_poll["question"]:
            return row_poll["question"], row_poll["topic_name"]
        elif row_prac and row_prac["question"]:
            return row_prac["question"], row_prac["topic_name"]
        return None, None


init_db()