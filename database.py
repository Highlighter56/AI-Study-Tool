import sqlite3
import json
from datetime import datetime

DB_NAME = "otto.db"


def _connect():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS questions (
        id TEXT PRIMARY KEY,
        path TEXT,
        question_text TEXT,
        question_type TEXT,
        options TEXT,
        classification TEXT,
        context TEXT,
        answer TEXT,
        suggested_mapping TEXT,
        answer_payload TEXT,
        confidence REAL,
        confidence_reasons TEXT,
        created_at TEXT
    )
    ''')

    cursor.execute("PRAGMA table_info(questions)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if "question_type" not in existing_columns:
        cursor.execute("ALTER TABLE questions ADD COLUMN question_type TEXT DEFAULT 'OTHER'")

    if "answer_payload" not in existing_columns:
        cursor.execute("ALTER TABLE questions ADD COLUMN answer_payload TEXT")

    if "confidence_reasons" not in existing_columns:
        cursor.execute("ALTER TABLE questions ADD COLUMN confidence_reasons TEXT")

    conn.commit()
    conn.close()

def save_question(q):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR REPLACE INTO questions (
        id,
        path,
        question_text,
        question_type,
        options,
        classification,
        context,
        answer,
        suggested_mapping,
        answer_payload,
        confidence,
        confidence_reasons,
        created_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    ''', (
        q.id,
        q.path,
        q.question_text,
        q.question_type,
        json.dumps(q.options), 
        q.classification,
        q.context,
        q.answer,
        json.dumps(q.suggested_mapping), 
        json.dumps(q.answer_payload),
        q.confidence,
        json.dumps(q.confidence_reasons),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

def get_question(q_id):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM questions WHERE id = ?", (q_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_latest_question():
    conn = _connect()
    cursor = conn.cursor()
    # Sort by the internal timestamp to find the most recent
    cursor.execute("SELECT * FROM questions ORDER BY created_at DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None