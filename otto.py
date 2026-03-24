import click
import json
import os
import shlex
import sys
import time
import uuid
from datetime import datetime
from vision import capture_and_interpret, get_model_fallbacks, DEFAULT_MODEL_FALLBACKS, probe_models, client
from settings_utils import get_configured_timeout_minutes
from database import (
    init_db,
    save_question,
    get_question,
    question_id_exists,
    get_latest_question,
    get_active_folder,
    create_folder,
    folder_exists,
    set_active_folder,
    get_setting,
    set_setting,
    list_folders_with_counts,
    list_folders_tree_with_counts,
    cycle_active_folder,
    move_folder,
    rename_folder,
    get_questions_by_folder,
    get_questions_for_study,
    move_capture_to_folder,
    delete_capture,
    delete_folder,
    save_study_run,
    update_study_run_outputs,
    get_latest_study_run,
    get_study_questions,
    save_feedback,
    list_feedback,
    get_feedback_for_prompt,
)
from models import OttoQuestion


QUESTION_TYPE_LABELS = {
    "MULTIPLE_CHOICE": "Multiple Choice",
    "TRUE_FALSE": "True/False",
    "FILL_IN_THE_BLANK": "Fill In The Blank",
    "CATEGORIZATION": "Categorization",
    "ORDERING": "Ordering",
    "SHORT_ANSWER": "Short Answer",
    "OTHER": "Other"
}

AI_WARNING_TEXT = (
    "AI-Generated Notice: This output may contain errors or omissions. "
    "Verify important information with trusted sources."
)

STUDY_QUESTION_TYPES = {
    "multiple_choice",
    "true_false",
    "short_answer",
    "fill_in_the_blank",
    "ordering",
    "categorization",
}

_runtime_mode = str(os.getenv("OTTO_RUN_MODE", "direct") or "direct").strip().lower()


def print_core_help(include_title=True):
    if include_title:
        click.echo(click.style("\nCore commands:", fg='cyan', bold=True))
    click.echo("\nHotkeys (listener mode):")
    click.echo("  Alt + Shift + Q : Capture")
    click.echo("  Alt + Shift + A : Answer (displays answer to latest captured question)")
    click.echo("  Alt + Shift + F : Show folders")
    click.echo("  Alt + Shift + R : Rotate active folder + show folders")
    click.echo("  Alt + Shift + K : Create folder")
    click.echo("  Alt + Shift + G : Generate study guide")
    click.echo("  Alt + Shift + Y : Mark latest capture correct")
    click.echo("  Alt + Shift + X : Mark latest capture incorrect")
    click.echo("  Alt + Shift + H : Show help menu")
    click.echo("  Alt + Shift + E : Exit listener")

    click.echo("\nCore commands:")
    click.echo("  python otto.py capture")
    click.echo("  python otto.py answer [Q_ID]     (Q_ID is optional)")
    click.echo("  python otto.py study-generate")
    click.echo("  python otto.py feedback-mark")
    click.echo("  python otto.py shell             (interactive text-command mode)")
    click.echo("  python otto.py help-menu")


def print_folder_help(include_title=True):
    if include_title:
        click.echo(click.style("\nFolder commands:", fg='cyan', bold=True))
    click.echo("  python otto.py folder-list [--list]")
    click.echo("  python otto.py folder-current")
    click.echo("  python otto.py folder-create [name]  (supports nested paths, e.g. unit1/section2)")
    click.echo("  python otto.py folder-set <name>")
    click.echo("  python otto.py folder-cycle")
    click.echo("  python otto.py folder-rename <old> <new>")
    click.echo("  python otto.py folder-move <source> <target-parent> [--create-target-parent]")
    click.echo("  python otto.py folder-delete <name> [--move-to X | --force] [--yes]")


def print_capture_help(include_title=True):
    if include_title:
        click.echo(click.style("\nCapture commands:", fg='cyan', bold=True))
    click.echo("  python otto.py capture")
    click.echo("  python otto.py answer [Q_ID]")
    click.echo("  python otto.py capture-list [folder] [--limit N]")
    click.echo("  python otto.py capture-move <Q_ID> <target-folder> [--create-target]")
    click.echo("  python otto.py capture-delete <Q_ID> [--yes]")


def print_settings_help(include_title=True):
    if include_title:
        click.echo(click.style("\nSettings commands:", fg='cyan', bold=True))
    click.echo("  python otto.py settings-show")
    click.echo("  python otto.py settings-set <clear_on_capture|clear_on_answer|clear_on_folder_view> <true|false>")
    click.echo("  python otto.py settings-set timeout_minutes <5-30>")


def print_model_help(include_title=True):
    if include_title:
        click.echo(click.style("\nModel commands:", fg='cyan', bold=True))
    click.echo("  python otto.py model-show")
    click.echo("  python otto.py model-probe [--apply] [--models comma,separated,list]")


def print_study_help(include_title=True):
    if include_title:
        click.echo(click.style("\nStudy commands:", fg='cyan', bold=True))
    click.echo("  python otto.py study-generate [--folder NAME] [--format md|txt|both]")
    click.echo("    Generate a study guide + optional practice questions from a folder tree.")
    click.echo("  python otto.py study-generate --interactive   (aliases: --customize, -i, -c)")
    click.echo("    In interactive mode folder prompt supports '?', 'list', or 'folder-list' to show tree.")
    click.echo("  python otto.py study-generate --question-count 25   (generate about this many questions)")
    click.echo("    Omit --question-count for auto target (hard cap 60).")
    click.echo("  python otto.py study-generate --mcq-only")
    click.echo("  python otto.py study-generate --question-order grouped|capture|random")


def print_feedback_help(include_title=True):
    if include_title:
        click.echo(click.style("\nFeedback commands:", fg='cyan', bold=True))
    click.echo("  python otto.py feedback-mark [TARGET_ID] --type capture|study --status correct|incorrect|unverified")
    click.echo("  python otto.py feedback-mark --interactive")
    click.echo("  python otto.py feedback-list [--folder NAME] [--status incorrect] [--limit 20]")


def print_help_menu():
    click.echo(click.style("\nAI-Study-Tool Help", fg='cyan', bold=True))
    
    click.echo(click.style("\nHelp commands:", fg='cyan', bold=True))
    click.echo("  python otto.py help-menu                 (show this menu)")
    click.echo("  python otto.py core-help                 (core commands)")
    click.echo("  python otto.py folder-help               (folder commands)")
    click.echo("  python otto.py capture-help              (capture commands)")
    click.echo("  python otto.py settings-help             (settings commands)")
    click.echo("  python otto.py model-help                (model commands)")
    click.echo("  python otto.py study-help                (study generation commands)")
    click.echo("  python otto.py feedback-help             (feedback/correction commands)")
    
    print_core_help()
    print_folder_help()
    print_capture_help()
    print_settings_help()
    print_model_help()
    print_study_help()
    print_feedback_help()

    click.echo("\nTip: Use '--help' on any command for detailed options.")


def _parse_json_response(raw_response):
    content = (raw_response or "").strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    return json.loads(content)


def _clear_pending_console_input():
    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getwch()
        return
    except Exception:
        pass


def _copy_to_clipboard(text):
    try:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(str(text))
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


def _parse_bool_setting(raw_value):
    text = str(raw_value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _is_setting_enabled(key, default=False):
    default_text = "true" if default else "false"
    parsed = _parse_bool_setting(get_setting(key, default_text))
    if parsed is None:
        return default
    return parsed


def _generate_unique_question_id(max_attempts=50):
    for _ in range(max_attempts):
        candidate = str(uuid.uuid4())[:5].upper()
        if not question_id_exists(candidate):
            return candidate

    for _ in range(max_attempts):
        candidate = str(uuid.uuid4())[:8].upper()
        if not question_id_exists(candidate):
            return candidate
    raise RuntimeError("Unable to generate a unique question ID")


def _get_timeout_minutes():
    return get_configured_timeout_minutes()


def _set_runtime_mode(mode):
    global _runtime_mode
    candidate = str(mode or "").strip().lower()
    _runtime_mode = candidate if candidate in {"listener", "shell", "direct"} else "direct"


def _get_runtime_mode():
    return _runtime_mode if _runtime_mode in {"listener", "shell", "direct"} else "direct"


def _print_followup_hints():
    mode = _get_runtime_mode()
    if mode == "listener":
        click.echo("Press Alt+Shift+A to reveal solution.")
        click.echo("Press Alt+Shift+F to show folder list.")
        click.echo("Press Alt+Shift+R to rotate folder.")
        click.echo("Press Alt+Shift+G to generate study material.")
        return

    if mode == "shell":
        click.echo("Try: answer")
        click.echo("Try: folder-list")
        click.echo("Try: folder-cycle")
        click.echo("Try: study-generate")
        return

    click.echo("Try: python otto.py answer")
    click.echo("Try: python otto.py folder-list")
    click.echo("Try: python otto.py folder-cycle")
    click.echo("Try: python otto.py study-generate")


def _read_shell_input_with_timeout(prompt_text, timeout_seconds, poll_seconds=0.10, history=None):
    try:
        import msvcrt
    except Exception:
        # Fallback for non-Windows environments.
        return input(prompt_text), False

    sys.stdout.write("\r")
    sys.stdout.write(prompt_text)
    sys.stdout.flush()
    prompt_started = time.time()

    deadline = time.time() + max(1.0, float(timeout_seconds))
    chars = []
    history_items = history if isinstance(history, list) else []
    history_index = len(history_items)
    rendered_len = len(prompt_text)

    def redraw():
        nonlocal rendered_len
        current_text = prompt_text + "".join(chars)
        current_len = len(current_text)
        pad = max(0, rendered_len - current_len)
        sys.stdout.write("\r")
        sys.stdout.write(current_text)
        if pad:
            sys.stdout.write(" " * pad)
        sys.stdout.write("\r")
        sys.stdout.write(current_text)
        sys.stdout.flush()
        rendered_len = current_len

    while True:
        if time.time() > deadline:
            sys.stdout.write("\n")
            sys.stdout.flush()
            return "", True

        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            deadline = time.time() + max(1.0, float(timeout_seconds))

            if ch in {"\r", "\n"}:
                if not chars and (time.time() - prompt_started) < 0.15:
                    # Ignore immediate stale Enter keypresses left in the console buffer.
                    continue
                sys.stdout.write("\n")
                sys.stdout.flush()
                return "".join(chars), False

            if ch == "\003":
                raise KeyboardInterrupt()

            if ch == "\b":
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue

            if ch in {"\xe0", "\x00"}:
                special = msvcrt.getwch()
                if special == "H" and history_items:
                    # Up arrow
                    history_index = max(0, history_index - 1)
                    chars = list(history_items[history_index])
                    redraw()
                elif special == "P" and history_items:
                    # Down arrow
                    history_index = min(len(history_items), history_index + 1)
                    if history_index == len(history_items):
                        chars = []
                    else:
                        chars = list(history_items[history_index])
                    redraw()
                continue

            if ch.isprintable():
                chars.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()
            continue

        time.sleep(poll_seconds)


def _safe_json_loads(raw_text, fallback):
    if isinstance(raw_text, (dict, list)):
        return raw_text
    try:
        parsed = json.loads(raw_text)
        return parsed if parsed is not None else fallback
    except Exception:
        return fallback


def _normalize_study_question_types(raw_types, mcq_only=False):
    if mcq_only:
        return ["multiple_choice"]

    items = [item.strip().lower() for item in str(raw_types or "").split(",") if item.strip()]
    normalized = []
    for item in items:
        candidate = item.replace("-", "_").replace(" ", "_")
        if candidate in STUDY_QUESTION_TYPES and candidate not in normalized:
            normalized.append(candidate)
    return normalized or [
        "multiple_choice",
        "true_false",
        "short_answer",
        "fill_in_the_blank",
        "ordering",
        "categorization",
    ]


def _sanitize_filename_piece(value):
    text = str(value or "").strip().replace("\\", "-").replace("/", "-")
    cleaned = []
    for ch in text:
        if ch.isalnum() or ch in {"-", "_"}:
            cleaned.append(ch)
    normalized = "".join(cleaned).strip("-_")
    return normalized or "study"


def _resolve_unique_output_base(base_path, fmt):
    wanted = str(fmt or "md").strip().lower()
    extensions = [".txt", ".md"] if wanted == "both" else [f".{wanted}"]

    def collides(candidate_base):
        for ext in extensions:
            if os.path.exists(candidate_base + ext):
                return True
        return False

    candidate = base_path
    if not collides(candidate):
        return candidate

    suffix = 1
    while True:
        next_candidate = f"{base_path}_{suffix}"
        if not collides(next_candidate):
            return next_candidate
        suffix += 1


def _open_generated_file(path_value):
    target = os.path.abspath(path_value)
    try:
        if os.name == "nt":
            os.startfile(target)  # type: ignore[attr-defined]
            return True, ""
    except Exception as exc:
        last_error = str(exc)
    else:
        last_error = ""

    try:
        click.launch(target)
        return True, ""
    except Exception as exc:
        if not last_error:
            last_error = str(exc)
        return False, last_error


def _study_depth_instruction(depth):
    mode = str(depth or "moderate").strip().lower()
    if mode == "refresher":
        return "Keep summaries concise and focused on quick recall."
    if mode == "indepth":
        return "Provide deeper conceptual explanation, common pitfalls, and detail-rich coverage."
    return "Provide balanced detail suitable for typical exam preparation."


def _resolve_question_limit(source_count, requested_limit=None):
    total = max(0, int(source_count or 0))
    auto_target = min(60, max(5, int(round(total * 0.75))))

    if requested_limit is None:
        return auto_target

    try:
        parsed = int(requested_limit)
    except Exception:
        return auto_target

    if parsed <= 0:
        return auto_target
    return min(60, max(1, parsed))


def _build_feedback_context_block(folder_name, question_type=None, limit=6, char_budget=1800):
    rows = get_feedback_for_prompt(folder_name, question_type=question_type, limit=limit)
    if not rows:
        return ""

    lines = ["Recent user corrections to prioritize:"]
    used = len(lines[0])
    for idx, row in enumerate(rows, start=1):
        qtype = str(row.get("question_type") or "unknown").strip()
        model_answer = str(row.get("model_answer") or "").strip()
        corrected = str(row.get("corrected_answer") or "").strip()
        note = str(row.get("note") or "").strip()
        text = f"{idx}. [{qtype}] model='{model_answer}'"
        if corrected:
            text += f" corrected='{corrected}'"
        if note:
            text += f" note='{note}'"

        if used + len(text) + 1 > char_budget:
            break
        lines.append(text)
        used += len(text) + 1

    return "\n".join(lines).strip()


def _resolve_feedback_target(target_type, target_id=None):
    normalized_type = str(target_type or "capture").strip().lower()
    provided_id = str(target_id or "").strip().upper()

    if normalized_type == "capture":
        if provided_id:
            return provided_id
        latest = get_latest_question()
        return str(latest.get("id") or "").strip().upper() if latest else ""

    if normalized_type == "study":
        if provided_id:
            return provided_id
        latest_run = get_latest_study_run()
        if not latest_run:
            return ""
        items = get_study_questions(latest_run.get("id"), limit=1)
        if not items:
            return ""
        return str(items[0].get("id") or "").strip().upper()

    return ""


def _build_study_prompt(folder_name, rows, include_summary, include_questions, question_types, depth, answer_key, title_hint="", question_limit=None):
    source_items = []
    for row in rows:
        options = _safe_json_loads(row.get("options"), [])
        context = str(row.get("context") or "").strip()
        source_items.append({
            "id": str(row.get("id") or ""),
            "folder": str(row.get("path") or ""),
            "question": str(row.get("question_text") or ""),
            "question_type": str(row.get("question_type") or "OTHER"),
            "answer": str(row.get("answer") or ""),
            "context": context,
            "options": options if isinstance(options, list) else [],
            "created_at": str(row.get("created_at") or ""),
        })

    max_questions = _resolve_question_limit(len(source_items), requested_limit=question_limit) if include_questions else 0
    prompt_payload = {
        "target_folder": folder_name,
        "title_hint": str(title_hint or "").strip(),
        "ai_warning": AI_WARNING_TEXT,
        "depth": depth,
        "depth_instruction": _study_depth_instruction(depth),
        "include_summary": include_summary,
        "include_questions": include_questions,
        "question_types": question_types,
        "max_questions": max_questions,
        "target_question_count": max_questions,
        "answer_key_required": bool(answer_key and include_questions),
        "source_items": source_items,
    }

    feedback_context = _build_feedback_context_block(folder_name, question_type=None, limit=6)

    return f"""
You are generating study material from previously captured educational questions.

Return strict JSON only. No markdown fences and no extra commentary.

Required schema:
{{
  "title": "string",
  "overview": "string",
  "sections": [
    {{
      "heading": "string",
      "summary": "string",
      "key_points": ["string"]
    }}
  ],
  "practice_questions": [
    {{
      "id": "Q1",
      "type": "multiple_choice|true_false|short_answer|fill_in_the_blank|ordering|categorization",
      "question": "string",
      "options": ["string"],
      "answer": "string",
      "explanation": "string",
      "source_folder": "string"
    }}
  ]
}}

Rules:
- If include_summary is false, return empty overview and empty sections array.
- If include_questions is false, return empty practice_questions array.
- Only use question types from question_types list.
- Aim to generate target_question_count questions and never exceed max_questions.
- Ensure answer and explanation exist for every generated practice question.
- Keep content educational, concrete, and aligned to provided source_items.

Known correction history (if any):
{feedback_context if feedback_context else "(none)"}

Input JSON:
{json.dumps(prompt_payload, ensure_ascii=True)}
""".strip()


def _generate_study_payload(prompt_text):
    model_fallbacks = get_model_fallbacks()
    last_error = ""

    for model_name in model_fallbacks:
        try:
            response = client.models.generate_content(model=model_name, contents=[prompt_text])
            payload = _parse_json_response(str(getattr(response, "text", "") or ""))
            if isinstance(payload, dict):
                payload["model_used"] = model_name
                return payload
        except Exception as exc:
            last_error = str(exc)
            continue

    raise RuntimeError(last_error or "All configured models failed to generate study content.")


def _render_study_markdown(payload, include_summary=True, include_questions=True, answer_key=True):
    title = str(payload.get("title") or "Study Guide").strip() or "Study Guide"
    overview = str(payload.get("overview") or "").strip()
    sections = payload.get("sections") if isinstance(payload.get("sections"), list) else []
    questions = payload.get("practice_questions") if isinstance(payload.get("practice_questions"), list) else []

    lines = [f"# {title}", "", f"> {AI_WARNING_TEXT}", ""]
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    if include_summary and (overview or sections):
        lines.append("## Summary")
        lines.append("")
        if overview:
            lines.append(overview)
            lines.append("")
        for section in sections:
            heading = str(section.get("heading") or "Topic").strip() or "Topic"
            summary = str(section.get("summary") or "").strip()
            key_points = section.get("key_points") if isinstance(section.get("key_points"), list) else []
            lines.append(f"### {heading}")
            if summary:
                lines.append(summary)
            for point in key_points:
                point_text = str(point).strip()
                if point_text:
                    lines.append(f"- {point_text}")
            lines.append("")

    if include_questions and questions:
        lines.append("## Practice Questions")
        lines.append("")
        for idx, item in enumerate(questions, start=1):
            qid = str(item.get("id") or "").strip()
            prompt = str(item.get("question") or "").strip()
            qtype = str(item.get("type") or "").strip().replace("_", " ").title()
            label = f"Q{idx}" if not qid else f"Q{idx} [{qid}]"
            lines.append(f"### {label}. {prompt}")
            if qtype:
                lines.append(f"Type: {qtype}")
            options = item.get("options") if isinstance(item.get("options"), list) else []
            for opt_index, option in enumerate(options, start=1):
                option_text = str(option).strip()
                if option_text:
                    lines.append(f"{opt_index}. {option_text}")
            lines.append("")

    if include_questions and answer_key and questions:
        lines.append("## Answer Key")
        lines.append("")
        lines.append(f"> {AI_WARNING_TEXT}")
        lines.append("")
        for idx, item in enumerate(questions, start=1):
            qid = str(item.get("id") or "").strip()
            answer = str(item.get("answer") or "").strip() or "(not provided)"
            explanation = str(item.get("explanation") or "").strip()
            label = f"Q{idx}" if not qid else f"Q{idx} [{qid}]"
            lines.append(f"- {label}: {answer}")
            if explanation:
                lines.append(f"  Explanation: {explanation}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _render_study_text(payload, include_summary=True, include_questions=True, answer_key=True):
    title = str(payload.get("title") or "Study Guide").strip() or "Study Guide"
    overview = str(payload.get("overview") or "").strip()
    sections = payload.get("sections") if isinstance(payload.get("sections"), list) else []
    questions = payload.get("practice_questions") if isinstance(payload.get("practice_questions"), list) else []

    lines = [title, "=" * len(title), "", AI_WARNING_TEXT, "", f"Generated: {datetime.now().isoformat(timespec='seconds')}", ""]

    if include_summary and (overview or sections):
        lines.extend(["SUMMARY", "-------"])
        if overview:
            lines.extend([overview, ""])
        for section in sections:
            heading = str(section.get("heading") or "Topic").strip() or "Topic"
            summary = str(section.get("summary") or "").strip()
            key_points = section.get("key_points") if isinstance(section.get("key_points"), list) else []
            lines.append(f"{heading}:")
            if summary:
                lines.append(f"  {summary}")
            for point in key_points:
                point_text = str(point).strip()
                if point_text:
                    lines.append(f"  - {point_text}")
            lines.append("")

    if include_questions and questions:
        lines.extend(["PRACTICE QUESTIONS", "------------------"])
        for idx, item in enumerate(questions, start=1):
            qid = str(item.get("id") or "").strip()
            prompt = str(item.get("question") or "").strip()
            qtype = str(item.get("type") or "").strip().replace("_", " ").title()
            label = f"Q{idx}" if not qid else f"Q{idx} [{qid}]"
            lines.append(f"{label}. {prompt}")
            if qtype:
                lines.append(f"Type: {qtype}")
            options = item.get("options") if isinstance(item.get("options"), list) else []
            for opt_index, option in enumerate(options, start=1):
                option_text = str(option).strip()
                if option_text:
                    lines.append(f"  {opt_index}. {option_text}")
            lines.append("")

    if include_questions and answer_key and questions:
        lines.extend(["ANSWER KEY", "----------", AI_WARNING_TEXT, ""])
        for idx, item in enumerate(questions, start=1):
            qid = str(item.get("id") or "").strip()
            answer = str(item.get("answer") or "").strip() or "(not provided)"
            explanation = str(item.get("explanation") or "").strip()
            label = f"Q{idx}" if not qid else f"Q{idx} [{qid}]"
            lines.append(f"{label}: {answer}")
            if explanation:
                lines.append(f"  Explanation: {explanation}")
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def _write_study_outputs(payload, folder_name, output_base, fmt, include_summary, include_questions, answer_key, title_hint=""):
    os.makedirs("captures", exist_ok=True)

    if output_base:
        raw_base = os.path.splitext(output_base)[0]
        base_path = raw_base
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_piece = _sanitize_filename_piece(folder_name)
        folder_parts = [part for part in str(folder_name or "").strip().replace("\\", "/").split("/") if part]
        grouped_dir = os.path.join("captures", "study_materials", *folder_parts) if folder_parts else os.path.join("captures", "study_materials")
        os.makedirs(grouped_dir, exist_ok=True)
        filename_title = _sanitize_filename_piece(title_hint) if str(title_hint or "").strip() else _sanitize_filename_piece(payload.get("title", ""))
        if filename_title and filename_title != "study":
            base_path = os.path.join(grouped_dir, f"study_material_{filename_title}_{folder_piece}_{timestamp}")
        else:
            base_path = os.path.join(grouped_dir, f"study_material_{folder_piece}_{timestamp}")

    base_path = _resolve_unique_output_base(base_path, fmt)

    generated = []

    if fmt in {"txt", "both"}:
        txt_path = base_path if base_path.lower().endswith(".txt") else f"{base_path}.txt"
        with open(txt_path, "w", encoding="utf-8") as handle:
            handle.write(_render_study_text(payload, include_summary, include_questions, answer_key))
        generated.append(txt_path)

    if fmt in {"md", "both"}:
        md_path = base_path if base_path.lower().endswith(".md") else f"{base_path}.md"
        with open(md_path, "w", encoding="utf-8") as handle:
            handle.write(_render_study_markdown(payload, include_summary, include_questions, answer_key))
        generated.append(md_path)

    return generated


def _normalize_question_type(raw_type, fallback_classification):
    value = str(raw_type or fallback_classification or "").strip().lower().replace("-", " ").replace("_", " ")

    if "categor" in value:
        return "CATEGORIZATION"
    if "chronolog" in value or "sequence" in value or "timeline" in value or "order" in value:
        return "ORDERING"
    if "fill" in value and "blank" in value:
        return "FILL_IN_THE_BLANK"
    if "true" in value and "false" in value:
        return "TRUE_FALSE"
    if "short" in value and "answer" in value:
        return "SHORT_ANSWER"
    if "multiple" in value or "mcq" in value or "choice" in value:
        return "MULTIPLE_CHOICE"
    return "OTHER"


def _normalize_options(raw_options):
    if isinstance(raw_options, list):
        return [str(item).strip() for item in raw_options if str(item).strip()]
    if isinstance(raw_options, str):
        chunks = [item.strip() for item in raw_options.replace("\n", ",").split(",")]
        return [item for item in chunks if item]
    return []


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None

    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y"}:
        return True
    if text in {"false", "f", "no", "n"}:
        return False
    return None


def _normalize_mapping(raw_mapping):
    if not isinstance(raw_mapping, dict):
        return {}

    normalized = {}
    for category, values in raw_mapping.items():
        category_name = str(category).strip()
        if not category_name:
            continue
        if isinstance(values, list):
            normalized[category_name] = [str(item).strip() for item in values if str(item).strip()]
        elif values is None:
            normalized[category_name] = []
        else:
            item_text = str(values).strip()
            normalized[category_name] = [item_text] if item_text else []
    return normalized


def _is_correct_bucket(label):
    text = str(label or "").strip().lower()
    return any(token in text for token in ["correct", "right", "true", "valid"])


def _is_incorrect_bucket(label):
    text = str(label or "").strip().lower()
    return any(token in text for token in ["incorrect", "wrong", "false", "invalid", "not correct"])


def _complete_categorization_mapping(categories, options):
    mapping = _normalize_mapping(categories)
    option_items = [str(item).strip() for item in (options or []) if str(item).strip()]

    assigned = set()
    for values in mapping.values():
        assigned.update(values)

    unassigned = [item for item in option_items if item not in assigned]

    has_correct = any(_is_correct_bucket(key) for key in mapping.keys())
    has_incorrect = any(_is_incorrect_bucket(key) for key in mapping.keys())

    if option_items and has_correct and not has_incorrect and unassigned:
        mapping["Incorrect"] = unassigned
        return mapping

    if option_items and has_incorrect and not has_correct and unassigned:
        mapping["Correct"] = unassigned
        return mapping

    if unassigned:
        mapping["Uncategorized"] = unassigned

    return mapping


def _normalize_answer_payload(data, question_type, options):
    payload = data.get("answer_payload") if isinstance(data.get("answer_payload"), dict) else {}
    answer = data.get("answer")

    if question_type == "MULTIPLE_CHOICE":
        selected = payload.get("selected_option", answer)
        selected_text = str(selected).strip() if selected is not None else ""
        if selected_text and options and selected_text not in options:
            for option in options:
                if selected_text.lower() in option.lower() or option.lower() in selected_text.lower():
                    selected_text = option
                    break
        return {"selected_option": selected_text}

    if question_type == "TRUE_FALSE":
        bool_value = payload.get("is_true")
        if bool_value is None:
            bool_value = answer
        parsed_bool = _parse_bool(bool_value)
        return {"is_true": parsed_bool}

    if question_type == "FILL_IN_THE_BLANK":
        blanks = payload.get("blanks")
        if isinstance(blanks, list):
            blank_values = [str(item).strip() for item in blanks if str(item).strip()]
        elif isinstance(answer, list):
            blank_values = [str(item).strip() for item in answer if str(item).strip()]
        elif isinstance(answer, str):
            chunks = [item.strip() for item in answer.replace("\n", ",").split(",")]
            blank_values = [item for item in chunks if item]
        else:
            blank_values = []
        return {"blanks": blank_values}

    if question_type == "CATEGORIZATION":
        categories = payload.get("categories")
        if not isinstance(categories, dict):
            categories = data.get("suggested_mapping")
        return {"categories": _normalize_mapping(categories)}

    if question_type == "ORDERING":
        ordered_items = payload.get("ordered_items")
        if isinstance(ordered_items, list):
            items = [str(item).strip() for item in ordered_items if str(item).strip()]
        elif isinstance(answer, list):
            items = [str(item).strip() for item in answer if str(item).strip()]
        elif isinstance(answer, str):
            chunks = [item.strip() for item in answer.replace("\n", ",").split(",")]
            items = [item for item in chunks if item]
        else:
            items = []
        return {"ordered_items": items}

    if question_type == "SHORT_ANSWER":
        short_answer = payload.get("short_answer", answer)
        return {"short_answer": str(short_answer).strip() if short_answer is not None else ""}

    other_answer = payload.get("other_answer", answer)
    return {"other_answer": str(other_answer).strip() if other_answer is not None else ""}


def _derive_primary_answer(question_type, answer_payload, fallback_answer):
    if question_type == "MULTIPLE_CHOICE":
        return answer_payload.get("selected_option") or (fallback_answer or "")
    if question_type == "TRUE_FALSE":
        value = answer_payload.get("is_true")
        if value is True:
            return "True"
        if value is False:
            return "False"
        return str(fallback_answer or "")
    if question_type == "FILL_IN_THE_BLANK":
        blanks = answer_payload.get("blanks") or []
        return ", ".join(blanks) if blanks else str(fallback_answer or "")
    if question_type == "CATEGORIZATION":
        categories = answer_payload.get("categories") or {}
        return "See category mapping" if categories else str(fallback_answer or "")
    if question_type == "ORDERING":
        items = answer_payload.get("ordered_items") or []
        return " -> ".join(items) if items else str(fallback_answer or "")
    if question_type == "SHORT_ANSWER":
        return answer_payload.get("short_answer") or str(fallback_answer or "")
    return answer_payload.get("other_answer") or str(fallback_answer or "")


def _safe_confidence(value):
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, conf))


def _calibrate_confidence(
    model_confidence,
    question_type,
    question_text,
    context,
    options,
    answer_text,
    answer_payload,
    model_reason=None
):
    base_confidence = _safe_confidence(model_confidence)
    penalty = 0.0
    reasons = []

    if model_reason:
        reasons.append(f"Model note: {str(model_reason).strip()}")

    question_text_len = len(str(question_text or "").strip())
    context_len = len(str(context or "").strip())

    if question_text_len < 12:
        penalty += 0.15
        reasons.append("Question text is very short or unclear.")

    if context_len < 40:
        penalty += 0.08
        reasons.append("Context is brief, which increases ambiguity risk.")

    if question_type in {"MULTIPLE_CHOICE", "TRUE_FALSE", "ORDERING"} and len(options) < 2:
        penalty += 0.20
        reasons.append("Expected options are incomplete for this question type.")

    if question_type == "MULTIPLE_CHOICE":
        selected_option = str(answer_payload.get("selected_option") or "").strip()
        if not selected_option:
            penalty += 0.20
            reasons.append("No clear selected option was identified.")
        elif options and selected_option not in options:
            penalty += 0.20
            reasons.append("Selected option did not match extracted options exactly.")

    elif question_type == "TRUE_FALSE":
        if answer_payload.get("is_true") is None:
            penalty += 0.25
            reasons.append("Could not confidently parse answer as True/False.")

    elif question_type == "FILL_IN_THE_BLANK":
        blanks = answer_payload.get("blanks") or []
        if not blanks:
            penalty += 0.20
            reasons.append("No blank-fill sequence was extracted.")

    elif question_type == "CATEGORIZATION":
        categories = _complete_categorization_mapping(answer_payload.get("categories") or {}, options)
        if not categories:
            penalty += 0.25
            reasons.append("No category mapping was extracted.")
        elif options:
            assigned = set()
            for values in categories.values():
                assigned.update(values)
            unassigned_count = len([item for item in options if item not in assigned])
            if unassigned_count > 0:
                ratio = unassigned_count / max(1, len(options))
                ratio_penalty = min(0.25, 0.25 * ratio)
                penalty += ratio_penalty
                reasons.append(f"{unassigned_count} option(s) were not confidently assigned to a category.")

    elif question_type == "ORDERING":
        ordered_items = answer_payload.get("ordered_items") or []
        if len(ordered_items) < 2:
            penalty += 0.20
            reasons.append("Could not confidently extract an ordering sequence.")

    if question_type == "OTHER":
        penalty += 0.10
        reasons.append("Question type could not be confidently classified.")

    if not str(answer_text or "").strip() and question_type != "CATEGORIZATION":
        penalty += 0.20
        reasons.append("Primary answer text is empty.")

    calibrated = max(0.0, min(1.0, base_confidence - penalty))

    if base_confidence >= 0.95 and penalty >= 0.15 and calibrated > 0.85:
        calibrated = 0.85
        reasons.append("High model confidence was capped due to structural uncertainty checks.")

    if not reasons:
        reasons.append("No structural quality issues detected.")

    return round(calibrated, 4), reasons


def _display_confidence_reasons(reasons):
    if not reasons:
        return
    click.echo(click.style("Confidence notes:", fg='yellow', bold=True))
    for reason in reasons[:3]:
        click.echo(f"  - {reason}")


def _display_answer(question_type, answer_text, answer_payload, mapping, options=None):
    if question_type == "MULTIPLE_CHOICE":
        selected = answer_payload.get("selected_option") or answer_text
        if selected:
            click.echo(f"\nAnswer: {selected}")
        return

    if question_type == "TRUE_FALSE":
        value = answer_payload.get("is_true")
        if value is True:
            click.echo("\nAnswer: True")
        elif value is False:
            click.echo("\nAnswer: False")
        elif answer_text:
            click.echo(f"\nAnswer: {answer_text}")
        return

    if question_type == "FILL_IN_THE_BLANK":
        blanks = answer_payload.get("blanks") or []
        if blanks:
            click.echo("\nAnswer order:")
            for idx, item in enumerate(blanks, start=1):
                click.echo(f"  {idx}. {item}")
        elif answer_text:
            click.echo(f"\nAnswer: {answer_text}")
        return

    if question_type == "CATEGORIZATION":
        categories = answer_payload.get("categories") or mapping or {}
        categories = _complete_categorization_mapping(categories, options)
        if categories:
            click.echo("\nCategory mapping:")
            for key, val in categories.items():
                click.echo(click.style(f"\n{key}:", bold=True))
                if val:
                    for item in val:
                        click.echo(f"  - {item}")
                else:
                    click.echo("  - (none)")
        elif answer_text:
            click.echo(f"\nAnswer: {answer_text}")
        return

    if question_type == "ORDERING":
        ordered_items = answer_payload.get("ordered_items") or []
        if ordered_items:
            click.echo("\nCorrect order:")
            for idx, item in enumerate(ordered_items, start=1):
                click.echo(f"  {idx}. {item}")
        elif answer_text:
            click.echo(f"\nAnswer: {answer_text}")
        return

    if answer_text:
        click.echo(f"\nAnswer: {answer_text}")

@click.group()
def cli():
    pass


@cli.command(name="help-menu")
def help_menu_cmd():
    print_help_menu()


@cli.command(name="core-help")
def core_help_cmd():
    print_core_help()


@cli.command(name="folder-help")
def folder_help_cmd():
    print_folder_help()


@cli.command(name="capture-help")
def capture_help_cmd():
    print_capture_help()


@cli.command(name="settings-help")
def settings_help_cmd():
    print_settings_help()


@cli.command(name="model-help")
def model_help_cmd():
    print_model_help()


@cli.command(name="study-help")
def study_help_cmd():
    print_study_help()


@cli.command(name="feedback-help")
def feedback_help_cmd():
    print_feedback_help()


@cli.command(name="feedback-mark")
@click.argument("target_id", required=False)
@click.option("--type", "target_type", type=click.Choice(["capture", "study"], case_sensitive=False), default="capture", show_default=True)
@click.option("--status", type=click.Choice(["correct", "incorrect", "unverified"], case_sensitive=False), default="correct", show_default=True)
@click.option("--corrected-answer", default="", help="Correct answer text when marking incorrect.")
@click.option("--note", default="", help="Optional note about the correction.")
@click.option("--interactive", is_flag=True, default=False, help="Prompt for status and correction fields.")
def feedback_mark_cmd(target_id, target_type, status, corrected_answer, note, interactive):
    selected_type = str(target_type or "capture").strip().lower()
    selected_status = str(status or "correct").strip().lower()
    selected_corrected = str(corrected_answer or "").strip()
    selected_note = str(note or "").strip()
    selected_target_id = str(target_id or "").strip().upper()

    if interactive:
        _clear_pending_console_input()
        selected_type = click.prompt(
            "Target type",
            default=selected_type,
            show_default=True,
            type=click.Choice(["capture", "study"], case_sensitive=False),
        ).lower()

        if selected_type == "study" and not selected_target_id:
            latest_run = get_latest_study_run()
            if latest_run:
                run_id = latest_run.get("id")
                run_rows = get_study_questions(run_id, limit=30)
                if run_rows:
                    click.echo(click.style("Latest study run questions:", fg='cyan', bold=True))
                    for row in run_rows:
                        pos = row.get("position")
                        qid = str(row.get("id") or "")
                        preview = str(row.get("question_text") or "").strip().replace("\n", " ")
                        short_preview = preview[:90] + ("..." if len(preview) > 90 else "")
                        click.echo(f"  {pos}. [{qid}] {short_preview}")
                    _clear_pending_console_input()
                    pick = click.prompt("Study question (enter SQ ID or list number)", default="", show_default=False).strip()
                    if pick.isdigit():
                        pos = int(pick)
                        selected = next((row for row in run_rows if int(row.get("position") or 0) == pos), None)
                        selected_target_id = str(selected.get("id") or "").strip().upper() if selected else ""
                    else:
                        selected_target_id = pick.upper()

        _clear_pending_console_input()
        selected_status = click.prompt(
            "Status",
            default=selected_status,
            show_default=True,
            type=click.Choice(["correct", "incorrect", "unverified"], case_sensitive=False),
        ).lower()

        if selected_status == "incorrect":
            _clear_pending_console_input()
            selected_note = click.prompt("What is wrong? (blank to skip)", default=selected_note, show_default=False).strip()
            _clear_pending_console_input()
            selected_corrected = click.prompt("What is the correct answer/text?", default=selected_corrected, show_default=False).strip()
        else:
            _clear_pending_console_input()
            selected_note = click.prompt("Note (blank to skip)", default=selected_note, show_default=False).strip()

    resolved_id = _resolve_feedback_target(selected_type, selected_target_id or target_id)
    if not resolved_id:
        if selected_type == "capture":
            click.echo(click.style("No capture target found. Provide TARGET_ID or capture first.", fg='red', bold=True))
        else:
            click.echo(click.style("No study question target found. Provide TARGET_ID or generate study material first.", fg='red', bold=True))
        return

    result = save_feedback(
        target_type=selected_type,
        target_id=resolved_id,
        status=selected_status,
        corrected_answer=selected_corrected,
        note=selected_note,
    )
    if not result.get("ok"):
        reason = result.get("reason")
        click.echo(click.style(f"Could not save feedback ({reason}).", fg='red', bold=True))
        return

    click.echo(click.style("Feedback saved.", fg='green', bold=True))
    click.echo(f"Target: {result.get('target_type')}:{result.get('target_id')} | Status: {result.get('status')}")


@cli.command(name="feedback-list")
@click.option("--folder", "folder_name", default="", help="Filter to folder subtree.")
@click.option("--type", "target_type", type=click.Choice(["capture", "study"], case_sensitive=False), default=None, help="Filter target type.")
@click.option("--status", type=click.Choice(["correct", "incorrect", "unverified"], case_sensitive=False), default=None, help="Filter status.")
@click.option("--limit", default=20, type=int, show_default=True)
def feedback_list_cmd(folder_name, target_type, status, limit):
    rows = list_feedback(
        limit=max(1, min(int(limit), 200)),
        folder_name=(folder_name or "").strip() or None,
        target_type=(target_type or "").strip() or None,
        status=(status or "").strip() or None,
    )

    if not rows:
        click.echo(click.style("No feedback entries found.", fg='yellow', bold=True))
        return

    click.echo(click.style(f"Feedback entries ({len(rows)}):", fg='cyan', bold=True))
    for row in rows:
        fid = row.get("id")
        target = f"{row.get('target_type')}:{row.get('target_id')}"
        folder = row.get("folder") or "general"
        entry_status = row.get("status")
        corrected = str(row.get("corrected_answer") or "").strip()
        corrected_note = f" | corrected: {corrected}" if corrected else ""
        click.echo(f"- #{fid} [{entry_status}] {target} @ {folder}{corrected_note}")


@cli.command(name="model-show")
def show_model_fallbacks_cmd():
    fallbacks = get_model_fallbacks()
    click.echo(click.style("Model fallbacks (in order):", fg='cyan', bold=True))
    for index, model_name in enumerate(fallbacks, start=1):
        click.echo(f"  {index}. {model_name}")


@cli.command(name="model-probe")
@click.option("--apply", is_flag=True, default=False, help="Save successful models as active fallback order.")
@click.option("--models", default="", help="Comma-separated model list to probe. Defaults to active fallback list + defaults.")
def probe_models_cmd(apply, models):
    provided = [item.strip() for item in str(models or "").split(",") if item.strip()]
    if provided:
        probe_list = provided
    else:
        seen = set()
        probe_list = []
        for name in get_model_fallbacks() + DEFAULT_MODEL_FALLBACKS:
            if name not in seen:
                seen.add(name)
                probe_list.append(name)

    click.echo(click.style(f"Probing {len(probe_list)} model(s)...", fg='cyan', bold=True))
    results = probe_models(probe_list)

    successes = [row["model"] for row in results if row.get("ok")]
    failures = [row for row in results if not row.get("ok")]

    if successes:
        click.echo(click.style("\nAvailable:", fg='green', bold=True))
        for model_name in successes:
            click.echo(f"  ✓ {model_name}")

    if failures:
        click.echo(click.style("\nUnavailable/failed:", fg='yellow', bold=True))
        for row in failures:
            err = str(row.get("error") or "Unknown error")
            click.echo(f"  ✗ {row.get('model')}: {err[:140]}")

    if apply:
        if not successes:
            click.echo(click.style("\nNo models succeeded; fallback list not updated.", fg='red', bold=True))
            return
        set_setting("model_fallbacks", ",".join(successes))
        click.echo(click.style("\nUpdated model_fallbacks setting from probe results.", fg='green', bold=True))


@cli.command(name="settings-show")
def settings_show_cmd():
    name_width = 20
    click.echo(click.style("Settings:", fg='cyan', bold=True))
    click.echo(f"  {'clear_on_capture':<{name_width}} = {get_setting('clear_on_capture', 'true')}   (clear terminal before capture output)")
    click.echo(f"  {'clear_on_answer':<{name_width}} = {get_setting('clear_on_answer', 'false')}   (clear terminal before answer output)")
    click.echo(f"  {'clear_on_folder_view':<{name_width}} = {get_setting('clear_on_folder_view', 'false')}   (clear before folder list/rotate output)")
    click.echo(f"  {'timeout_minutes':<{name_width}} = {_get_timeout_minutes()}   (listener + shell inactivity timeout)")
    model_setting = get_setting("model_fallbacks", "")
    click.echo(f"  {'model_fallbacks':<{name_width}} = {model_setting if model_setting else '<default order>'}   (comma-separated model order)")


@cli.command(name="settings-set")
@click.argument("key")
@click.argument("value")
def settings_set_cmd(key, value):
    normalized_key = str(key or "").strip().lower()
    bool_allowed = {"clear_on_capture", "clear_on_answer", "clear_on_folder_view"}
    if normalized_key == "timeout_minutes":
        try:
            parsed_minutes = int(str(value).strip())
        except Exception:
            click.echo(click.style("timeout_minutes must be an integer from 5 to 30.", fg='red', bold=True))
            return
        if parsed_minutes < 5 or parsed_minutes > 30:
            click.echo(click.style("timeout_minutes must be between 5 and 30.", fg='red', bold=True))
            return
        saved = set_setting(normalized_key, str(parsed_minutes))
        click.echo(click.style(f"Updated {normalized_key} = {saved}", fg='green', bold=True))
        return

    if normalized_key not in bool_allowed:
        click.echo(click.style(
            "Unsupported setting key. Use clear_on_capture, clear_on_answer, clear_on_folder_view, or timeout_minutes.",
            fg='red',
            bold=True
        ))
        return

    parsed = _parse_bool_setting(value)
    if parsed is None:
        click.echo(click.style("Value must be true/false.", fg='red', bold=True))
        return

    saved = set_setting(normalized_key, "true" if parsed else "false")
    click.echo(click.style(f"Updated {normalized_key} = {saved}", fg='green', bold=True))


@cli.command(name="study-generate")
@click.option("--folder", "folder_name", default="", help="Source folder. Defaults to active folder.")
@click.option("--format", "fmt", type=click.Choice(["txt", "md", "both"], case_sensitive=False), default="md", show_default=True)
@click.option("--output", "output_base", default="", help="Output base path (without extension) or full file path.")
@click.option("--title", "title_hint", default="", help="Optional title to guide generated study guide heading.")
@click.option("--open/--no-open", "open_output", default=True, show_default=True, help="Open generated file after creation.")
@click.option("--include-summary/--no-summary", default=True, show_default=True)
@click.option("--include-questions/--no-questions", default=True, show_default=True)
@click.option("--question-types", default="multiple_choice,true_false,short_answer,fill_in_the_blank,ordering,categorization", show_default=True)
@click.option("--mcq-only", is_flag=True, default=False, help="Shortcut for --question-types multiple_choice.")
@click.option("--question-order", type=click.Choice(["grouped", "capture", "random"], case_sensitive=False), default="grouped", show_default=True)
@click.option(
    "--question-count",
    "--max-questions",
    "question_count",
    type=int,
    default=None,
    help="Generate this many practice questions. Omit for auto target (hard cap 60)."
)
@click.option("--depth", type=click.Choice(["refresher", "moderate", "indepth"], case_sensitive=False), default="moderate", show_default=True)
@click.option("--answer-key/--no-answer-key", default=True, show_default=True)
@click.option("--interactive", "interactive", is_flag=True, default=False, help="Interactive setup mode.")
@click.option("--customize", "customize", is_flag=True, default=False, help="Alias for --interactive.")
@click.option("-i", "interactive_short", is_flag=True, default=False, help="Short alias for --interactive.")
@click.option("-c", "customize_short", is_flag=True, default=False, help="Short alias for --interactive.")
def study_generate_cmd(
    folder_name,
    fmt,
    output_base,
    title_hint,
    open_output,
    include_summary,
    include_questions,
    question_types,
    mcq_only,
    question_order,
    question_count,
    depth,
    answer_key,
    interactive,
    customize,
    interactive_short,
    customize_short,
):
    interactive_mode = bool(interactive or customize or interactive_short or customize_short)
    target_folder = (folder_name or "").strip() or get_active_folder()
    selected_format = str(fmt or "md").lower()
    selected_order = str(question_order or "grouped").lower()
    selected_depth = str(depth or "moderate").lower()
    selected_title = str(title_hint or "").strip()
    selected_question_count = int(question_count) if question_count is not None else None

    if interactive_mode:
        click.echo(click.style("Interactive study generation setup", fg='cyan', bold=True))
        click.echo(click.style("This wizard asks about 8-12 prompts depending your choices.", fg='cyan'))
        click.echo("You can enter '?', 'list', or 'folder-list' to view folder tree before choosing.")
        while True:
            proposed_folder = click.prompt("Folder", default=target_folder, show_default=True).strip()
            lowered = proposed_folder.lower()
            if lowered in {"?", "list", "folder-list"}:
                _print_folders_table(show_tree=True)
                continue
            if folder_exists(proposed_folder):
                target_folder = proposed_folder
                break
            click.echo(click.style(f"Folder does not exist: {proposed_folder}", fg='red', bold=True))

        selected_format = click.prompt(
            "Output format",
            default=selected_format,
            show_default=True,
            type=click.Choice(["txt", "md", "both"], case_sensitive=False),
        ).lower()
        selected_title = click.prompt(
            "Study guide title (blank for auto)",
            default=selected_title,
            show_default=False,
        ).strip()

        include_summary = click.confirm("Include summary section?", default=include_summary)
        include_questions = click.confirm("Include practice questions?", default=include_questions)

        if include_questions:
            answer_key = click.confirm("Include answer key?", default=answer_key)
        else:
            answer_key = False

        if include_summary:
            selected_depth = click.prompt(
                "Summary depth",
                default=selected_depth,
                show_default=True,
                type=click.Choice(["refresher", "moderate", "indepth"], case_sensitive=False),
            ).lower()

        if include_questions:
            mcq_only = click.confirm("MCQ only mode?", default=mcq_only)
            if not mcq_only:
                question_types = click.prompt(
                    "Question types (comma-separated)",
                    default=question_types,
                    show_default=True,
                )
            selected_order = click.prompt(
                "Question order",
                default=selected_order,
                show_default=True,
                type=click.Choice(["grouped", "capture", "random"], case_sensitive=False),
            ).lower()
            default_count_text = "" if selected_question_count is None else str(selected_question_count)
            while True:
                raw_count = click.prompt(
                    "Question count (blank = auto target, hard cap 60)",
                    default=default_count_text,
                    show_default=False,
                ).strip()
                if not raw_count:
                    selected_question_count = None
                    break
                try:
                    parsed_count = int(raw_count)
                except Exception:
                    click.echo(click.style("Question count must be a whole number or blank.", fg='red', bold=True))
                    continue
                if parsed_count <= 0:
                    click.echo(click.style("Question count must be at least 1, or blank for auto.", fg='red', bold=True))
                    continue
                selected_question_count = parsed_count
                break

        output_base = click.prompt(
            "Output path base (blank for auto, e.g. captures/unit1_midterm)",
            default=output_base,
            show_default=False,
        ).strip()
        open_output = click.confirm("Open generated file after save?", default=open_output)

        if not click.confirm("Generate study guide now?", default=True):
            click.echo("Cancelled.")
            return

    if not folder_exists(target_folder):
        click.echo(click.style(f"Folder does not exist: {target_folder}", fg='red', bold=True))
        click.echo("Use folder-create first, then rerun study-generate.")
        return

    if not include_summary and not include_questions:
        click.echo(click.style("Nothing to generate: enable summary and/or questions.", fg='red', bold=True))
        return

    if selected_question_count is not None and selected_question_count <= 0:
        click.echo(click.style("--question-count must be 1 or greater when provided.", fg='red', bold=True))
        return

    selected_types = _normalize_study_question_types(question_types, mcq_only=mcq_only)
    if mcq_only and str(question_types or "").strip():
        click.echo(click.style("--mcq-only enabled; ignoring --question-types.", fg='yellow'))

    rows = get_questions_for_study(target_folder, order_mode=selected_order)
    if not rows:
        click.echo(click.style(f"No captures found in folder tree: {target_folder}", fg='yellow', bold=True))
        return

    question_cap = _resolve_question_limit(len(rows), requested_limit=selected_question_count) if include_questions else 0
    if include_questions and selected_question_count is None:
        cap_message = f"Source captures: {len(rows)} | Question target: {question_cap} (auto target, hard cap 60; model may return fewer)"
    elif include_questions:
        cap_message = f"Source captures: {len(rows)} | Question target: {question_cap} (manual target, hard cap 60; model may return fewer)"
    else:
        cap_message = f"Source captures: {len(rows)}"
    click.echo(click.style(cap_message, fg='cyan'))

    prompt_text = _build_study_prompt(
        folder_name=target_folder,
        rows=rows,
        include_summary=include_summary,
        include_questions=include_questions,
        question_types=selected_types,
        depth=selected_depth,
        answer_key=answer_key,
        title_hint=selected_title,
        question_limit=selected_question_count,
    )

    click.echo(click.style("Generating study material...", fg='cyan', bold=True))
    try:
        payload = _generate_study_payload(prompt_text)
    except Exception as exc:
        click.echo(click.style(f"Study generation failed: {exc}", fg='red', bold=True))
        return

    run_info = {"run_id": "", "questions": []}
    questions_for_save = payload.get("practice_questions") if isinstance(payload.get("practice_questions"), list) else []
    if include_questions and questions_for_save:
        try:
            run_info = save_study_run(
                folder_name=target_folder,
                title=selected_title or payload.get("title") or "",
                model_used=payload.get("model_used") or "unknown",
                output_files=[],
                questions=questions_for_save,
            )
            saved_ids = [row.get("id") for row in run_info.get("questions", [])]
            for idx, item in enumerate(questions_for_save):
                if idx < len(saved_ids):
                    item["id"] = saved_ids[idx]
        except Exception as exc:
            click.echo(click.style(f"Warning: could not persist study question IDs ({exc}).", fg='yellow'))

    try:
        output_files = _write_study_outputs(
            payload=payload,
            folder_name=target_folder,
            output_base=output_base,
            fmt=selected_format,
            include_summary=include_summary,
            include_questions=include_questions,
            answer_key=answer_key,
            title_hint=selected_title,
        )
    except Exception as exc:
        click.echo(click.style(f"Could not write study output files: {exc}", fg='red', bold=True))
        return

    if run_info.get("run_id"):
        try:
            update_study_run_outputs(run_info.get("run_id"), output_files)
        except Exception:
            pass

    click.echo(click.style("Study material generated.", fg='green', bold=True))
    click.echo(click.style(f"Model Used: {payload.get('model_used', 'unknown')}", fg='white'))
    if run_info.get("run_id"):
        click.echo(click.style(f"Study Run ID: {run_info.get('run_id')}", fg='cyan'))
    click.echo(click.style(AI_WARNING_TEXT, fg='yellow', bold=True))
    for file_path in output_files:
        click.echo(f"Saved: {file_path}")

    if open_output and output_files:
        preferred = None
        for file_path in output_files:
            if file_path.lower().endswith(".md"):
                preferred = file_path
                break
        target = preferred or output_files[0]
        ok, error_message = _open_generated_file(target)
        if not ok:
            click.echo(click.style(f"Could not open generated file: {error_message}", fg='yellow'))


@cli.command(name="shell")
def shell_cmd():
    timeout_minutes = _get_timeout_minutes()
    click.echo(click.style("Interactive mode. Type 'help' for menu, 'exit' to quit.", fg='cyan', bold=True))
    click.echo(click.style(f"Auto-timeout: {timeout_minutes} minutes of inactivity.", fg='yellow'))
    command_history = []
    while True:
        # Avoid stray buffered keypresses (especially CR/LF) from creating empty prompt lines.
        _clear_pending_console_input()
        timeout_seconds = _get_timeout_minutes() * 60
        try:
            raw, timed_out = _read_shell_input_with_timeout("otto> ", timeout_seconds, history=command_history)
            if timed_out:
                click.echo(click.style("Shell timed out due to inactivity.", fg='yellow', bold=True))
                return
            raw = str(raw or "").strip()
        except (EOFError, KeyboardInterrupt):
            click.echo("\nExiting shell.")
            return

        if not raw:
            continue

        if not command_history or command_history[-1] != raw:
            command_history.append(raw)
            if len(command_history) > 200:
                command_history = command_history[-200:]

        lowered = raw.lower()
        if lowered in {"exit", "quit"}:
            click.echo("Exiting shell.")
            return
        if lowered in {"help", "?"}:
            print_help_menu()
            continue

        try:
            args = shlex.split(raw)
        except ValueError as error:
            click.echo(click.style(f"Parse error: {error}", fg='red'))
            continue

        if not args:
            continue

        if args[0].lower() == "python":
            args = args[1:]
        if args and args[0].lower().endswith("otto.py"):
            args = args[1:]

        if not args:
            continue

        if args[0] == "shell":
            click.echo("Already in shell mode.")
            continue

        previous_mode = _get_runtime_mode()
        try:
            _set_runtime_mode("shell")
            cli.main(args=args, prog_name="otto.py", standalone_mode=False)
        except SystemExit:
            continue
        except click.ClickException as error:
            error.show()
        except Exception as error:
            click.echo(click.style(f"Command error: {error}", fg='red'))
        finally:
            _set_runtime_mode(previous_mode)
            _clear_pending_console_input()


@cli.command(name="folder-set")
@click.argument("folder_name")
def set_folder_cmd(folder_name):
    folder = set_active_folder(folder_name, create_if_missing=False)
    if not folder:
        click.echo(click.style(f"Folder does not exist: {folder_name}", fg='red', bold=True))
        click.echo("Use folder-create first, then folder-set.")
        return
    click.echo(click.style(f"Active folder set to: {folder}", fg='green', bold=True))


@cli.command(name="folder-create")
@click.argument("folder_name", required=False)
def create_folder_cmd(folder_name):
    if folder_name:
        result = create_folder(folder_name)
        if not result["created"]:
            click.echo(click.style(f"Folder already exists: {result['name']}", fg='red', bold=True))
            return
        click.echo(click.style(f"Folder created: {result['name']}", fg='green', bold=True))
        return

    while True:
        _clear_pending_console_input()
        proposed = click.prompt("Folder name").strip()
        result = create_folder(proposed)
        if result["created"]:
            click.echo(click.style(f"Folder created: {result['name']}", fg='green', bold=True))
            return
        click.echo(click.style(f"Folder already exists: {result['name']}. Try another name.", fg='red'))


@cli.command(name="folder-rename")
@click.argument("old_name")
@click.argument("new_name")
def rename_folder_cmd(old_name, new_name):
    result = rename_folder(old_name, new_name)
    if not result.get("ok"):
        reason = result.get("reason")
        if reason == "old-missing":
            click.echo(click.style(f"Folder not found: {result.get('old')}", fg='red', bold=True))
            return
        if reason == "new-exists":
            click.echo(click.style(f"Folder already exists: {result.get('new')}", fg='red', bold=True))
            return
        if reason == "same-name":
            click.echo(click.style("Old and new folder names are the same.", fg='yellow', bold=True))
            return
        click.echo(click.style("Could not rename folder.", fg='red', bold=True))
        return

    click.echo(click.style(
        f"Folder renamed: {result.get('old')} -> {result.get('new')}",
        fg='green',
        bold=True
    ))


@cli.command(name="folder-current")
def current_folder_cmd():
    folder = get_active_folder()
    click.echo(click.style(f"Current folder: {folder}", fg='blue', bold=True))


@cli.command(name="folder-list")
@click.option("--list", "show_list", is_flag=True, default=False, help="Show folders in flat list form.")
def list_folders_cmd(show_list):
    _print_folders_table(show_tree=not show_list)


@cli.command(name="folder-move")
@click.argument("source_folder")
@click.argument("target_parent")
@click.option("--create-target-parent", is_flag=True, default=False, help="Create target parent path if missing.")
def move_folder_cmd(source_folder, target_parent, create_target_parent):
    result = move_folder(source_folder, target_parent, create_target_parent=create_target_parent)
    if not result.get("ok"):
        reason = result.get("reason")
        if reason == "protected-default":
            click.echo(click.style("Cannot move the default folder.", fg='red', bold=True))
            return
        if reason == "source-missing":
            click.echo(click.style(f"Source folder not found: {result.get('source')}", fg='red', bold=True))
            return
        if reason == "target-parent-missing":
            click.echo(click.style(f"Target parent not found: {result.get('target_parent')}", fg='red', bold=True))
            click.echo("Use --create-target-parent to create the parent path.")
            return
        if reason == "target-inside-source":
            click.echo(click.style("Cannot move a folder into itself or its descendants.", fg='red', bold=True))
            return
        if reason == "same-target":
            click.echo(click.style("Folder is already at that location.", fg='yellow', bold=True))
            return
        if reason == "name-conflict":
            click.echo(click.style(f"Name conflict at destination: {result.get('target')}", fg='red', bold=True))
            click.echo("Rename the source folder first or pick a different target parent.")
            return
        click.echo(click.style("Could not move folder.", fg='red', bold=True))
        return

    click.echo(click.style(
        f"Moved folder {result.get('source')} -> {result.get('destination')}",
        fg='green',
        bold=True
    ))
    click.echo(f"Updated {result.get('moved_folders')} folder path(s) and {result.get('moved_questions')} capture path(s).")


def _print_folders_table(show_tree=False):
    if _is_setting_enabled("clear_on_folder_view", default=False):
        click.clear()

    active = get_active_folder()
    folders = list_folders_tree_with_counts() if show_tree else list_folders_with_counts()
    if not folders:
        click.echo("No folders found.")
        return

    names = [folder["name"] for folder in folders]
    next_name = None
    if names:
        active_idx = names.index(active) if active in names else -1
        if active_idx >= 0:
            next_name = names[(active_idx + 1) % len(names)]

    rendered_rows = []
    for folder in folders:
        folder_name = folder["name"]
        depth = int(folder.get("depth") or 0)
        leaf = folder.get("leaf") or folder_name
        display_name = folder_name
        if show_tree:
            indent = "  " * depth
            display_name = leaf if depth == 0 else f"{indent}/{leaf}"
        rendered_rows.append({
            "name": folder_name,
            "count": int(folder.get("count") or 0),
            "display": display_name,
        })

    name_width = max(22, min(70, max(len(row["display"]) for row in rendered_rows)))

    heading = "Folders (tree):" if show_tree else "Folders:"
    click.echo(click.style(heading, fg='cyan', bold=True))
    click.echo(f"{'STATUS':<8}  {'NAME':<{name_width}}  COUNT")
    click.echo(f"{'-' * 8}  {'-' * name_width}  {'-' * 5}")
    for row in rendered_rows:
        folder_name = row["name"]

        status = ""
        line = f"{row['display']:<{name_width}}  {row['count']:>5}"
        if folder_name == active:
            status = "ACTIVE"
            click.echo(click.style(f"{status:<8}  {line}", fg='green', bold=True))
        elif folder_name == next_name:
            status = "NEXT"
            click.echo(click.style(f"{status:<8}  {line}", fg='yellow'))
        else:
            click.echo(f"{'':<8}  {line}")


@cli.command(name="capture-list")
@click.argument("folder_name", required=False)
@click.option("--limit", default=20, show_default=True, type=int)
def list_questions_cmd(folder_name, limit):
    folder = (folder_name or get_active_folder()).strip().lower()
    rows = get_questions_by_folder(folder, limit=max(1, min(limit, 200)))
    if not rows:
        click.echo(click.style(f"No questions found in folder: {folder}", fg='yellow', bold=True))
        return

    click.echo(click.style(f"Questions in '{folder}' (latest {len(rows)}):", fg='cyan', bold=True))
    for row in rows:
        qid = row.get("id", "?????")
        qtype = row.get("classification") or row.get("question_type") or "Unknown"
        question_text = str(row.get("question_text") or "").strip().replace("\n", " ")
        preview = question_text[:90] + ("..." if len(question_text) > 90 else "")
        click.echo(f"- [{qid}] ({qtype}) {preview}")


@cli.command(name="capture-move")
@click.argument("q_id")
@click.argument("target_folder")
@click.option("--create-target", is_flag=True, default=False, help="Create target folder if missing.")
def move_capture_cmd(q_id, target_folder, create_target):
    result = move_capture_to_folder(q_id, target_folder, create_target=create_target)
    if not result.get("ok"):
        reason = result.get("reason")
        if reason == "missing-id":
            click.echo(click.style("Capture ID is required.", fg='red', bold=True))
            return
        if reason == "missing-capture":
            click.echo(click.style(f"Capture not found: {q_id}", fg='red', bold=True))
            return
        if reason == "target-missing":
            click.echo(click.style(f"Target folder not found: {result.get('target')}", fg='red', bold=True))
            click.echo("Use create-folder first or pass --create-target.")
            return
        click.echo(click.style("Could not move capture.", fg='red', bold=True))
        return

    click.echo(click.style(
        f"Moved capture {result.get('id')} from {result.get('from')} to {result.get('to')}",
        fg='green',
        bold=True
    ))


@cli.command(name="capture-delete")
@click.argument("q_id")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt.")
def delete_capture_cmd(q_id, yes):
    if not yes:
        proceed = click.confirm(f"Delete capture {q_id.upper()}?", default=False)
        if not proceed:
            click.echo("Cancelled.")
            return

    result = delete_capture(q_id)
    if not result.get("ok"):
        reason = result.get("reason")
        if reason == "missing-id":
            click.echo(click.style("Capture ID is required.", fg='red', bold=True))
            return
        if reason == "missing-capture":
            click.echo(click.style(f"Capture not found: {q_id}", fg='red', bold=True))
            return
        click.echo(click.style("Could not delete capture.", fg='red', bold=True))
        return

    click.echo(click.style(
        f"Deleted capture {result.get('id')} from folder {result.get('from')}",
        fg='green',
        bold=True
    ))


@cli.command(name="folder-delete")
@click.argument("folder_name")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt.")
@click.option("--move-to", default=None, help="Move folder captures to another folder before deleting.")
@click.option("--force", is_flag=True, default=False, help="Delete all captures in folder.")
def delete_folder_cmd(folder_name, yes, move_to, force):
    if not yes:
        if move_to:
            prompt = f"Delete folder {folder_name} and move captures to {move_to}?"
        elif force:
            prompt = f"Delete folder {folder_name} and permanently delete its captures?"
        else:
            prompt = f"Delete folder {folder_name}?"
        proceed = click.confirm(prompt, default=False)
        if not proceed:
            click.echo("Cancelled.")
            return

    result = delete_folder(folder_name, force=force, move_to=move_to)
    if not result.get("ok"):
        reason = result.get("reason")
        if reason == "protected-default":
            click.echo(click.style("Cannot delete default folder unless you move captures with --move-to.", fg='red', bold=True))
            return
        if reason == "missing-folder":
            click.echo(click.style(f"Folder not found: {result.get('folder')}", fg='red', bold=True))
            return
        if reason == "same-target":
            click.echo(click.style("--move-to folder must be different from folder being deleted.", fg='red', bold=True))
            return
        if reason == "not-empty":
            click.echo(click.style(
                f"Folder has {result.get('count')} captures. Use --move-to <folder> or --force.",
                fg='red',
                bold=True
            ))
            return
        click.echo(click.style("Could not delete folder.", fg='red', bold=True))
        return

    moved_count = int(result.get("moved_count") or 0)
    deleted_count = int(result.get("deleted_count") or 0)
    moved_to = result.get("moved_to")
    click.echo(click.style(f"Deleted folder: {result.get('folder')}", fg='green', bold=True))
    if moved_to:
        click.echo(f"Moved {moved_count} capture(s) to {moved_to}.")
    if deleted_count:
        click.echo(f"Deleted {deleted_count} capture(s).")


@cli.command(name="folder-cycle")
def cycle_folder_cmd():
    next_folder = cycle_active_folder()
    click.echo(click.style(f"Active folder switched to: {next_folder}", fg='green', bold=True))
    _print_folders_table(show_tree=True)

@cli.command()
def capture():
    active_folder = get_active_folder()
    feedback_context = _build_feedback_context_block(active_folder, question_type=None, limit=6)
    raw_response = capture_and_interpret(correction_context=feedback_context)
    
    try:
        data = _parse_json_response(raw_response)
        
        if "error" in data:
            click.echo(click.style(f"❌ AI Error: {data.get('details', 'Unknown')}", fg='red'))
            return

        q_id = _generate_unique_question_id()
        active_folder = get_active_folder()
        question_type = _normalize_question_type(data.get("question_type"), data.get("classification"))
        options = _normalize_options(data.get("options", []))
        answer_payload = _normalize_answer_payload(data, question_type, options)
        answer_text = _derive_primary_answer(question_type, answer_payload, data.get("answer"))
        suggested_mapping = answer_payload.get("categories") if question_type == "CATEGORIZATION" else None
        calibrated_confidence, confidence_reasons = _calibrate_confidence(
            model_confidence=data.get('confidence', 0.0),
            question_type=question_type,
            question_text=data.get('question_text', ''),
            context=data.get('context', ''),
            options=options,
            answer_text=answer_text,
            answer_payload=answer_payload,
            model_reason=data.get('confidence_reason')
        )
        
        question = OttoQuestion(
            id=q_id,
            path=active_folder,
            question_text=data.get('question_text', 'No text found'),
            question_type=question_type,
            classification=QUESTION_TYPE_LABELS.get(question_type, data.get('classification', 'Unknown')),
            options=options,
            context=data.get('context', 'No context available'),
            answer=answer_text,
            suggested_mapping=suggested_mapping,
            answer_payload=answer_payload,
            model_used=str(data.get('model_used', 'unknown')),
            confidence=calibrated_confidence,
            confidence_reasons=confidence_reasons
        )
        
        save_question(question)

        if _copy_to_clipboard(q_id):
            clipboard_note = f"Question ID copied to clipboard: {q_id}"
        else:
            clipboard_note = f"Question ID: {q_id}"
        
        # --- DISPLAY OUTPUT ---
        if _is_setting_enabled("clear_on_capture", default=True):
            click.clear()
        
        # 1. Header
        click.echo(click.style(f"[{question.classification}] ID: {q_id}", fg='blue', bold=True))
        click.echo(click.style(f"Folder: {question.path}", fg='white', bold=True))
        
        # 2. Confidence Score (Purple/Magenta) - High Visibility at top
        conf_percent = int(question.confidence * 100)
        click.echo(click.style(f"AI Confidence: {conf_percent}%", fg='magenta', bold=True))
        click.echo(click.style(f"Model Used: {question.model_used}", fg='white'))
        click.echo(click.style(AI_WARNING_TEXT, fg='yellow', bold=True))
        _display_confidence_reasons(question.confidence_reasons)
        
        # 3. Question
        click.echo(click.style(f"\nQ: {question.question_text}", bold=True))
        
        # 4. Context 
        click.echo("_" * 50)
        click.echo(click.style("CONTEXT:", fg='cyan', underline=True))
        click.echo(question.context)
        click.echo("_" * 50)
        _print_followup_hints()
        click.echo(clipboard_note)
        
    except Exception as e:
        click.echo(f"Processing error: {e}")

@cli.command()
@click.argument('q_id', required=False)
def answer(q_id):
    row = get_question(q_id.upper()) if q_id else get_latest_question()

    if not row:
        click.echo("No question found.")
        return

    if _is_setting_enabled("clear_on_answer", default=False):
        click.clear()

    display_id = row.get("id")
    folder = row.get("path") or "general"
    ans = row.get("answer")
    mapping_str = row.get("suggested_mapping")
    options_str = row.get("options")
    payload_str = row.get("answer_payload")
    model_used = row.get("model_used") or "unknown"
    reasons_str = row.get("confidence_reasons")
    conf = _safe_confidence(row.get("confidence", 0.0))
    question_type = row.get("question_type") or _normalize_question_type(None, row.get("classification"))

    mapping = {}
    if mapping_str and mapping_str != "null":
        try:
            mapping = _normalize_mapping(json.loads(mapping_str))
        except Exception:
            mapping = {}

    answer_payload = {}
    if payload_str and payload_str != "null":
        try:
            payload_candidate = json.loads(payload_str)
            if isinstance(payload_candidate, dict):
                answer_payload = payload_candidate
        except Exception:
            answer_payload = {}

    if not answer_payload:
        answer_payload = _normalize_answer_payload(
            {"answer": ans, "suggested_mapping": mapping},
            question_type,
            []
        )

    confidence_reasons = []
    if reasons_str and reasons_str != "null":
        try:
            parsed_reasons = json.loads(reasons_str)
            if isinstance(parsed_reasons, list):
                confidence_reasons = [str(item).strip() for item in parsed_reasons if str(item).strip()]
        except Exception:
            confidence_reasons = []

    options = []
    if options_str and options_str != "null":
        try:
            options_candidate = json.loads(options_str)
            options = _normalize_options(options_candidate)
        except Exception:
            options = []
    
    # --- DISPLAY SOLUTION ---
    click.echo(click.style(f"\n💡 SOLUTION [{display_id}]", fg='green', bold=True))
    click.echo(click.style(f"Folder: {folder}", fg='white', bold=True))
    
    # Confidence Score (Purple/Magenta)
    click.echo(click.style(f"AI Confidence: {int(conf * 100)}%", fg='magenta', bold=True))
    click.echo(click.style(f"Model Used: {model_used}", fg='white'))
    click.echo(click.style(AI_WARNING_TEXT, fg='yellow', bold=True))
    _display_confidence_reasons(confidence_reasons)

    _display_answer(question_type, ans, answer_payload, mapping, options)

if __name__ == "__main__":
    init_db()
    if str(os.getenv("OTTO_RUN_MODE", "")).strip().lower() == "listener":
        _clear_pending_console_input()
    cli()