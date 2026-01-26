import sqlite3
import json
from datetime import datetime

DB_NAME = "otto.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS questions (
        id TEXT PRIMARY KEY,
        path TEXT,
        question_text TEXT,
        options TEXT,
        classification TEXT,
        context TEXT,
        answer TEXT,
        suggested_mapping TEXT,
        confidence REAL,
        created_at TEXT
    )
    ''')
    conn.commit()
    conn.close()

def save_question(q):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR REPLACE INTO questions VALUES (?,?,?,?,?,?,?,?,?,?)
    ''', (
        q.id, q.path, q.question_text, 
        json.dumps(q.options), 
        q.classification, q.context, q.answer, 
        json.dumps(q.suggested_mapping), 
        q.confidence, datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()

def get_question(q_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM questions WHERE id = ?", (q_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_latest_question():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Sort by the internal timestamp to find the most recent
    cursor.execute("SELECT * FROM questions ORDER BY created_at DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row