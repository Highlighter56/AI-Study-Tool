import sqlite3
import json
import random
import uuid
from datetime import datetime

DB_NAME = "otto.db"
DEFAULT_FOLDER = "general"

DEFAULT_SETTINGS = {
    "active_folder": DEFAULT_FOLDER,
    "clear_on_capture": "true",
    "clear_on_answer": "false",
    "clear_on_folder_view": "false",
    "timeout_minutes": "10",
    "model_fallbacks": "",
    "feedback_context_mode": "full",
    "feedback_max_items": "6",
    "feedback_char_budget": "1800",
}


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
        model_used TEXT,
        confidence REAL,
        confidence_reasons TEXT,
        created_at TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS folders (
        name TEXT PRIMARY KEY,
        created_at TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS study_runs (
        id TEXT PRIMARY KEY,
        folder TEXT,
        title TEXT,
        model_used TEXT,
        output_files TEXT,
        created_at TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS study_questions (
        id TEXT PRIMARY KEY,
        run_id TEXT,
        position INTEGER,
        question_text TEXT,
        question_type TEXT,
        model_answer TEXT,
        explanation TEXT,
        source_folder TEXT,
        created_at TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_type TEXT,
        target_id TEXT,
        folder TEXT,
        question_type TEXT,
        status TEXT,
        model_answer TEXT,
        corrected_answer TEXT,
        note TEXT,
        created_at TEXT
    )
    ''')

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_study_questions_run_id ON study_questions(run_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_target ON feedback(target_type, target_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_folder ON feedback(folder)")

    cursor.execute("PRAGMA table_info(questions)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if "question_type" not in existing_columns:
        cursor.execute("ALTER TABLE questions ADD COLUMN question_type TEXT DEFAULT 'OTHER'")

    if "answer_payload" not in existing_columns:
        cursor.execute("ALTER TABLE questions ADD COLUMN answer_payload TEXT")

    if "confidence_reasons" not in existing_columns:
        cursor.execute("ALTER TABLE questions ADD COLUMN confidence_reasons TEXT")

    if "model_used" not in existing_columns:
        cursor.execute("ALTER TABLE questions ADD COLUMN model_used TEXT")

    for key, value in DEFAULT_SETTINGS.items():
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
    cursor.execute(
        "INSERT OR IGNORE INTO folders (name, created_at) VALUES (?, ?)",
        (DEFAULT_FOLDER, datetime.now().isoformat())
    )

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
        model_used,
        confidence,
        confidence_reasons,
        created_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
        q.model_used,
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


def question_id_exists(q_id):
    normalized = str(q_id or "").strip().upper()
    if not normalized:
        return False
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM questions WHERE id = ?", (normalized,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def get_latest_question():
    conn = _connect()
    cursor = conn.cursor()
    # Sort by the internal timestamp to find the most recent
    cursor.execute("SELECT * FROM questions ORDER BY created_at DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def _normalize_folder_name(folder_name):
    text = str(folder_name or "").strip().replace("\\", "/")
    if not text:
        return DEFAULT_FOLDER

    parts = [part.strip().lower() for part in text.split("/") if part.strip() and part.strip() != "."]
    if not parts:
        return DEFAULT_FOLDER
    return "/".join(parts)


def _folder_ancestors(folder_name):
    normalized = _normalize_folder_name(folder_name)
    parts = normalized.split("/")
    ancestors = []
    for index in range(1, len(parts) + 1):
        ancestors.append("/".join(parts[:index]))
    return ancestors


def create_folder(folder_name):
    normalized = _normalize_folder_name(folder_name)
    conn = _connect()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM folders WHERE name = ?", (normalized,))
    exists = cursor.fetchone() is not None

    now_text = datetime.now().isoformat()
    for ancestor in _folder_ancestors(normalized):
        cursor.execute(
            "INSERT OR IGNORE INTO folders (name, created_at) VALUES (?, ?)",
            (ancestor, now_text)
        )

    conn.commit()
    conn.close()
    return {"name": normalized, "created": not exists}


def folder_exists(folder_name):
    normalized = _normalize_folder_name(folder_name)
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM folders WHERE name = ?", (normalized,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def get_active_folder():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'active_folder'")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return DEFAULT_FOLDER
    return _normalize_folder_name(row["value"])


def get_setting(key, default=None):
    setting_key = str(key or "").strip()
    if not setting_key:
        return default
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (setting_key,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return default
    return row["value"]


def set_setting(key, value):
    setting_key = str(key or "").strip()
    setting_value = "" if value is None else str(value).strip()
    if not setting_key:
        return None
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (setting_key, setting_value)
    )
    conn.commit()
    conn.close()
    return setting_value


def set_active_folder(folder_name, create_if_missing=False):
    normalized = _normalize_folder_name(folder_name)
    if not folder_exists(normalized):
        if not create_if_missing:
            return None
        create_folder(normalized)
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_folder', ?)",
        (normalized,)
    )
    conn.commit()
    conn.close()
    return normalized


def list_folders_with_counts():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM folders ORDER BY name")
    folder_rows = cursor.fetchall()

    cursor.execute("SELECT path, COUNT(*) as cnt FROM questions GROUP BY path")
    count_rows = cursor.fetchall()
    count_map = {
        _normalize_folder_name(row["path"]): int(row["cnt"] or 0)
        for row in count_rows
    }

    folder_names = set()
    for row in folder_rows:
        folder_names.update(_folder_ancestors(row["name"]))
    for question_path in count_map.keys():
        folder_names.update(_folder_ancestors(question_path))

    folders = []
    for folder_name in folder_names:
        folders.append({"name": folder_name, "count": count_map.get(folder_name, 0)})

    active_folder = get_active_folder()
    if not any(item["name"] == active_folder for item in folders):
        folders.append({"name": active_folder, "count": 0})

    folders.sort(key=lambda item: item["name"])
    conn.close()
    return folders


def list_folders_tree_with_counts():
    flat = list_folders_with_counts()
    by_name = {item["name"]: int(item.get("count") or 0) for item in flat}

    children_map = {}
    roots = set()
    for full_name in by_name.keys():
        parts = full_name.split("/")
        if len(parts) == 1:
            roots.add(full_name)
            continue

        parent = "/".join(parts[:-1])
        children_map.setdefault(parent, []).append(full_name)

    rows = []

    def walk(node_name):
        depth = node_name.count("/")
        rows.append({
            "name": node_name,
            "leaf": node_name.split("/")[-1],
            "depth": depth,
            "count": by_name.get(node_name, 0),
        })
        for child in sorted(children_map.get(node_name, []), key=lambda item: item.split("/")[-1]):
            walk(child)

    for root_name in sorted(roots, key=lambda item: item.split("/")[-1]):
        walk(root_name)

    return rows


def cycle_active_folder():
    folders = list_folders_tree_with_counts()
    names = [item["name"] for item in folders]
    if not names:
        return set_active_folder(DEFAULT_FOLDER, create_if_missing=True)

    current = get_active_folder()
    if current not in names:
        return set_active_folder(names[0], create_if_missing=True)

    current_idx = names.index(current)
    next_idx = (current_idx + 1) % len(names)
    return set_active_folder(names[next_idx], create_if_missing=True)


def get_questions_by_folder(folder_name, limit=20):
    normalized = _normalize_folder_name(folder_name)
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM questions WHERE path = ? ORDER BY created_at DESC LIMIT ?",
        (normalized, int(limit))
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_questions_for_study(folder_name, order_mode="grouped", limit=None):
    normalized = _normalize_folder_name(folder_name)
    mode = str(order_mode or "grouped").strip().lower()

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM questions WHERE path = ? OR path LIKE ?",
        (normalized, normalized + "/%")
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if mode == "capture":
        rows.sort(key=lambda row: str(row.get("created_at") or ""))
    elif mode == "random":
        random.shuffle(rows)
    else:
        rows.sort(key=lambda row: (str(row.get("path") or ""), str(row.get("created_at") or "")))

    if limit is not None:
        try:
            limited = max(0, int(limit))
        except Exception:
            limited = 0
        rows = rows[:limited]

    return rows


def move_capture_to_folder(question_id, target_folder, create_target=False):
    qid = str(question_id or "").strip().upper()
    if not qid:
        return {"ok": False, "reason": "missing-id"}

    target = _normalize_folder_name(target_folder)
    if not folder_exists(target):
        if not create_target:
            return {"ok": False, "reason": "target-missing", "target": target}
        create_folder(target)

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT path FROM questions WHERE id = ?", (qid,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return {"ok": False, "reason": "missing-capture", "id": qid}

    source = _normalize_folder_name(row["path"])
    cursor.execute("UPDATE questions SET path = ? WHERE id = ?", (target, qid))
    conn.commit()
    conn.close()
    return {"ok": True, "id": qid, "from": source, "to": target}


def delete_capture(question_id):
    qid = str(question_id or "").strip().upper()
    if not qid:
        return {"ok": False, "reason": "missing-id"}

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT path FROM questions WHERE id = ?", (qid,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return {"ok": False, "reason": "missing-capture", "id": qid}

    source = _normalize_folder_name(row["path"])
    cursor.execute("DELETE FROM questions WHERE id = ?", (qid,))
    conn.commit()
    conn.close()
    return {"ok": True, "id": qid, "from": source}


def delete_folder(folder_name, force=False, move_to=None):
    target = _normalize_folder_name(folder_name)

    if target == DEFAULT_FOLDER and not move_to:
        return {"ok": False, "reason": "protected-default", "folder": target}

    if not folder_exists(target):
        return {"ok": False, "reason": "missing-folder", "folder": target}

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM folders WHERE name = ? OR name LIKE ? ORDER BY LENGTH(name) DESC",
        (target, target + "/%")
    )
    subtree_folders = [str(row["name"]) for row in cursor.fetchall()]

    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM questions WHERE path = ? OR path LIKE ?",
        (target, target + "/%")
    )
    count = int(cursor.fetchone()["cnt"] or 0)

    move_target = None
    if move_to:
        move_target = _normalize_folder_name(move_to)
        if _is_descendant_path(move_target, target):
            conn.close()
            return {"ok": False, "reason": "same-target", "folder": target}
        if not folder_exists(move_target):
            now_text = datetime.now().isoformat()
            for ancestor in _folder_ancestors(move_target):
                cursor.execute(
                    "INSERT OR IGNORE INTO folders (name, created_at) VALUES (?, ?)",
                    (ancestor, now_text)
                )

    if count > 0 and not force and not move_target:
        conn.close()
        return {"ok": False, "reason": "not-empty", "folder": target, "count": count}

    moved_count = 0
    deleted_count = 0
    if count > 0 and move_target:
        cursor.execute(
            "SELECT path FROM questions WHERE path = ? OR path LIKE ?",
            (target, target + "/%")
        )
        question_paths = sorted({str(row["path"]) for row in cursor.fetchall()}, key=len, reverse=True)
        for old_path in question_paths:
            suffix = old_path[len(target):]
            new_path = move_target + suffix
            cursor.execute("UPDATE questions SET path = ? WHERE path = ?", (new_path, old_path))
            moved_count += int(cursor.rowcount or 0)
    elif count > 0 and force:
        cursor.execute("DELETE FROM questions WHERE path = ? OR path LIKE ?", (target, target + "/%"))
        deleted_count = count

    cursor.execute("SELECT value FROM settings WHERE key = 'active_folder'")
    active_row = cursor.fetchone()
    active = _normalize_folder_name(active_row["value"]) if active_row else DEFAULT_FOLDER

    for folder_path in subtree_folders:
        cursor.execute("DELETE FROM folders WHERE name = ?", (folder_path,))

    if _is_descendant_path(active, target):
        replacement = move_target or DEFAULT_FOLDER
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_folder', ?)",
            (replacement,)
        )
        cursor.execute(
            "INSERT OR IGNORE INTO folders (name, created_at) VALUES (?, ?)",
            (replacement, datetime.now().isoformat())
        )

    conn.commit()
    conn.close()
    return {
        "ok": True,
        "folder": target,
        "moved_to": move_target,
        "moved_count": moved_count,
        "deleted_count": deleted_count,
    }


def _is_descendant_path(path_value, parent_value):
    if not parent_value:
        return False
    return path_value == parent_value or path_value.startswith(parent_value + "/")


def move_folder(source_folder, target_parent, create_target_parent=False):
    source = _normalize_folder_name(source_folder)
    parent_text = str(target_parent or "").strip().replace("\\", "/")
    target_parent_normalized = ""
    if parent_text not in {"", "/", "."}:
        target_parent_normalized = _normalize_folder_name(parent_text)

    if source == DEFAULT_FOLDER:
        return {"ok": False, "reason": "protected-default", "folder": source}

    source_leaf = source.split("/")[-1]
    destination = f"{target_parent_normalized}/{source_leaf}" if target_parent_normalized else source_leaf

    if destination == source:
        return {"ok": False, "reason": "same-target", "source": source, "target": destination}

    if target_parent_normalized and _is_descendant_path(target_parent_normalized, source):
        return {"ok": False, "reason": "target-inside-source", "source": source, "target_parent": target_parent_normalized}

    conn = _connect()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM folders WHERE name = ?", (source,))
    if cursor.fetchone() is None:
        conn.close()
        return {"ok": False, "reason": "source-missing", "source": source}

    if target_parent_normalized:
        cursor.execute("SELECT 1 FROM folders WHERE name = ?", (target_parent_normalized,))
        parent_exists = cursor.fetchone() is not None
        if not parent_exists:
            if not create_target_parent:
                conn.close()
                return {"ok": False, "reason": "target-parent-missing", "target_parent": target_parent_normalized}
            now_text = datetime.now().isoformat()
            for ancestor in _folder_ancestors(target_parent_normalized):
                cursor.execute(
                    "INSERT OR IGNORE INTO folders (name, created_at) VALUES (?, ?)",
                    (ancestor, now_text)
                )

    cursor.execute("SELECT 1 FROM folders WHERE name = ?", (destination,))
    if cursor.fetchone() is not None:
        conn.close()
        return {"ok": False, "reason": "name-conflict", "target": destination}

    cursor.execute(
        "SELECT name FROM folders WHERE name = ? OR name LIKE ? ORDER BY LENGTH(name) ASC",
        (source, source + "/%")
    )
    source_rows = [str(row["name"]) for row in cursor.fetchall()]
    if not source_rows:
        conn.close()
        return {"ok": False, "reason": "source-missing", "source": source}

    mapping = []
    for old_name in source_rows:
        suffix = old_name[len(source):]
        new_name = destination + suffix
        mapping.append((old_name, new_name))

    target_names = {new_name for _, new_name in mapping}
    for new_name in target_names:
        cursor.execute("SELECT 1 FROM folders WHERE name = ?", (new_name,))
        row = cursor.fetchone()
        if row is not None and new_name not in source_rows:
            conn.close()
            return {"ok": False, "reason": "name-conflict", "target": new_name}

    tmp_prefix = f"__tmp_move__{int(datetime.now().timestamp() * 1000)}__"
    for old_name, _ in mapping:
        cursor.execute("UPDATE folders SET name = ? WHERE name = ?", (tmp_prefix + old_name, old_name))

    for old_name, new_name in mapping:
        cursor.execute("UPDATE folders SET name = ? WHERE name = ?", (new_name, tmp_prefix + old_name))

    moved_questions = 0
    for old_name, new_name in mapping:
        cursor.execute("UPDATE questions SET path = ? WHERE path = ?", (new_name, old_name))
        moved_questions += int(cursor.rowcount or 0)

    cursor.execute("SELECT value FROM settings WHERE key = 'active_folder'")
    active_row = cursor.fetchone()
    if active_row:
        active = _normalize_folder_name(active_row["value"])
        if _is_descendant_path(active, source):
            active_suffix = active[len(source):]
            active_replacement = destination + active_suffix
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_folder', ?)",
                (active_replacement,)
            )

    conn.commit()
    conn.close()
    return {
        "ok": True,
        "source": source,
        "target_parent": target_parent_normalized,
        "destination": destination,
        "moved_folders": len(mapping),
        "moved_questions": moved_questions,
    }


def rename_folder(old_name, new_name):
    old_normalized = _normalize_folder_name(old_name)
    new_normalized = _normalize_folder_name(new_name)

    if old_normalized == new_normalized:
        return {"ok": False, "reason": "same-name", "old": old_normalized, "new": new_normalized}

    conn = _connect()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM folders WHERE name = ?", (old_normalized,))
    if cursor.fetchone() is None:
        conn.close()
        return {"ok": False, "reason": "old-missing", "old": old_normalized, "new": new_normalized}

    cursor.execute("SELECT 1 FROM folders WHERE name = ?", (new_normalized,))
    if cursor.fetchone() is not None:
        conn.close()
        return {"ok": False, "reason": "new-exists", "old": old_normalized, "new": new_normalized}

    cursor.execute(
        "SELECT name FROM folders WHERE name = ? OR name LIKE ? ORDER BY LENGTH(name) ASC",
        (old_normalized, old_normalized + "/%")
    )
    source_rows = [str(row["name"]) for row in cursor.fetchall()]
    if not source_rows:
        conn.close()
        return {"ok": False, "reason": "old-missing", "old": old_normalized, "new": new_normalized}

    mapping = []
    for old_path in source_rows:
        suffix = old_path[len(old_normalized):]
        mapping.append((old_path, new_normalized + suffix))

    target_names = {new_path for _, new_path in mapping}
    for new_path in target_names:
        cursor.execute("SELECT 1 FROM folders WHERE name = ?", (new_path,))
        row = cursor.fetchone()
        if row is not None and new_path not in source_rows:
            conn.close()
            return {"ok": False, "reason": "new-exists", "old": old_normalized, "new": new_normalized}

    tmp_prefix = f"__tmp_rename__{int(datetime.now().timestamp() * 1000)}__"
    for old_path, _ in mapping:
        cursor.execute("UPDATE folders SET name = ? WHERE name = ?", (tmp_prefix + old_path, old_path))

    for old_path, new_path in mapping:
        cursor.execute("UPDATE folders SET name = ? WHERE name = ?", (new_path, tmp_prefix + old_path))

    for old_path, new_path in mapping:
        cursor.execute("UPDATE questions SET path = ? WHERE path = ?", (new_path, old_path))

    cursor.execute("SELECT value FROM settings WHERE key = 'active_folder'")
    row = cursor.fetchone()
    if row:
        active = _normalize_folder_name(row["value"])
        if _is_descendant_path(active, old_normalized):
            active_suffix = active[len(old_normalized):]
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_folder', ?)",
                (new_normalized + active_suffix,)
            )

    conn.commit()
    conn.close()
    return {"ok": True, "old": old_normalized, "new": new_normalized}


def _new_id(prefix):
    return f"{prefix}{str(uuid.uuid4())[:8].upper()}"


def save_study_run(folder_name, title, model_used, output_files, questions):
    run_id = _new_id("SR")
    created_text = datetime.now().isoformat()
    normalized_folder = _normalize_folder_name(folder_name)

    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO study_runs (id, folder, title, model_used, output_files, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            run_id,
            normalized_folder,
            str(title or "").strip(),
            str(model_used or "unknown").strip(),
            json.dumps(output_files or []),
            created_text,
        ),
    )

    saved_questions = []
    for idx, item in enumerate(questions or [], start=1):
        qid = _new_id("SQ")
        question_type = str(item.get("type") or "").strip().lower().replace("-", "_")
        question_text = str(item.get("question") or "").strip()
        model_answer = str(item.get("answer") or "").strip()
        explanation = str(item.get("explanation") or "").strip()
        source_folder = _normalize_folder_name(item.get("source_folder") or normalized_folder)

        cursor.execute(
            "INSERT INTO study_questions (id, run_id, position, question_text, question_type, model_answer, explanation, source_folder, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (qid, run_id, idx, question_text, question_type, model_answer, explanation, source_folder, created_text),
        )
        saved_questions.append({
            "id": qid,
            "position": idx,
            "question": question_text,
            "type": question_type,
            "answer": model_answer,
            "source_folder": source_folder,
        })

    conn.commit()
    conn.close()
    return {"run_id": run_id, "questions": saved_questions}


def get_latest_study_run():
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM study_runs ORDER BY created_at DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_study_run_outputs(run_id, output_files):
    rid = str(run_id or "").strip()
    if not rid:
        return False
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE study_runs SET output_files = ? WHERE id = ?",
        (json.dumps(output_files or []), rid)
    )
    changed = int(cursor.rowcount or 0) > 0
    conn.commit()
    conn.close()
    return changed


def get_study_questions(run_id, limit=100):
    rid = str(run_id or "").strip()
    if not rid:
        return []
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM study_questions WHERE run_id = ? ORDER BY position ASC LIMIT ?",
        (rid, max(1, min(500, int(limit))))
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_study_question(question_id):
    qid = str(question_id or "").strip().upper()
    if not qid:
        return None
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM study_questions WHERE id = ?", (qid,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def save_feedback(target_type, target_id, status, corrected_answer=None, note=None):
    normalized_target_type = str(target_type or "").strip().lower()
    normalized_status = str(status or "").strip().lower().replace("_", "-")
    if normalized_status == "assumed-correct":
        normalized_status = "unverified"
    normalized_target_id = str(target_id or "").strip().upper()
    corrected_text = str(corrected_answer or "").strip()
    note_text = str(note or "").strip()

    if normalized_target_type not in {"capture", "study"}:
        return {"ok": False, "reason": "invalid-target-type"}
    if normalized_status not in {"correct", "incorrect", "unverified"}:
        return {"ok": False, "reason": "invalid-status"}
    if not normalized_target_id:
        return {"ok": False, "reason": "missing-target-id"}

    folder = ""
    question_type = ""
    model_answer = ""
    if normalized_target_type == "capture":
        row = get_question(normalized_target_id)
        if not row:
            return {"ok": False, "reason": "missing-capture", "target_id": normalized_target_id}
        folder = _normalize_folder_name(row.get("path") or DEFAULT_FOLDER)
        question_type = str(row.get("question_type") or "").strip()
        model_answer = str(row.get("answer") or "").strip()
    else:
        row = get_study_question(normalized_target_id)
        if not row:
            return {"ok": False, "reason": "missing-study-question", "target_id": normalized_target_id}
        folder = _normalize_folder_name(row.get("source_folder") or DEFAULT_FOLDER)
        question_type = str(row.get("question_type") or "").strip()
        model_answer = str(row.get("model_answer") or "").strip()

    conn = _connect()
    cursor = conn.cursor()
    created_text = datetime.now().isoformat()
    cursor.execute(
        "INSERT INTO feedback (target_type, target_id, folder, question_type, status, model_answer, corrected_answer, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            normalized_target_type,
            normalized_target_id,
            folder,
            question_type,
            normalized_status,
            model_answer,
            corrected_text,
            note_text,
            created_text,
        ),
    )
    feedback_id = int(cursor.lastrowid)
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "id": feedback_id,
        "target_type": normalized_target_type,
        "target_id": normalized_target_id,
        "status": normalized_status,
    }


def list_feedback(limit=20, folder_name=None, target_type=None, status=None):
    sql = "SELECT * FROM feedback WHERE 1=1"
    params = []

    if folder_name:
        normalized_folder = _normalize_folder_name(folder_name)
        sql += " AND (folder = ? OR folder LIKE ?)"
        params.extend([normalized_folder, normalized_folder + "/%"])

    if target_type:
        sql += " AND target_type = ?"
        params.append(str(target_type).strip().lower())

    if status:
        normalized_status = str(status).strip().lower().replace("_", "-")
        if normalized_status == "assumed-correct":
            normalized_status = "unverified"
        sql += " AND status = ?"
        params.append(normalized_status)

    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(500, int(limit))))

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(sql, tuple(params))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_feedback_for_prompt(folder_name, question_type=None, limit=6, include_scores=False):
    """
    Retrieve feedback for prompt injection with optional scoring info for debugging.
    
    Returns list of feedback dicts, optionally with scoring metadata.
    """
    normalized_folder = _normalize_folder_name(folder_name)
    qtype = str(question_type or "").strip().upper()

    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM feedback WHERE status = 'incorrect' ORDER BY created_at DESC LIMIT 300")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    scored = []
    for row in rows:
        row_folder = _normalize_folder_name(row.get("folder") or DEFAULT_FOLDER)
        folder_score = 0.0
        type_score = 0.0
        content_score = 0.0
        
        # Folder proximity scoring
        if _is_descendant_path(normalized_folder, row_folder) or _is_descendant_path(row_folder, normalized_folder):
            folder_score = 0.95
        elif normalized_folder.split("/")[0] == row_folder.split("/")[0]:
            folder_score = 0.60
        else:
            folder_score = 0.30
        
        # Question type matching
        if qtype and str(row.get("question_type") or "").strip().upper() == qtype:
            type_score = 1.0
        else:
            type_score = 0.8
        
        # Content quality (has correction)
        if str(row.get("corrected_answer") or "").strip():
            content_score = 1.0
        else:
            content_score = 0.5
        
        # Combined score (weighted average)
        combined = (folder_score * 0.5) + (type_score * 0.3) + (content_score * 0.2)
        
        timestamp = str(row.get("created_at") or "")
        row_with_score = dict(row)
        
        if include_scores:
            row_with_score["_folder_score"] = folder_score
            row_with_score["_type_score"] = type_score
            row_with_score["_content_score"] = content_score
            row_with_score["_combined_score"] = combined
        
        scored.append((combined, timestamp, row_with_score))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected = [item[2] for item in scored[:max(1, min(20, int(limit)))]]
    return selected