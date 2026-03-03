import click
import json
import shlex
import uuid
from vision import capture_and_interpret, get_model_fallbacks
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
    cycle_active_folder,
    rename_folder,
    get_questions_by_folder,
    move_capture_to_folder,
    delete_capture,
    delete_folder,
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


def print_help_menu():
    click.echo(click.style("\nAI-Study-Tool Help", fg='cyan', bold=True))
    click.echo("\nHotkeys (listener mode):")
    click.echo("  Alt + Shift + Q : Capture")
    click.echo("  Alt + Shift + A : Answer (displays answer to latest captured question)")
    click.echo("  Alt + Shift + F : Show folders")
    click.echo("  Alt + Shift + R : Rotate active folder + show folders")
    click.echo("  Alt + Shift + K : Create folder")
    click.echo("  Alt + Shift + H : Show help menu")
    click.echo("  Alt + Shift + E : Exit listener")

    click.echo("\nCore commands:")
    click.echo("  python otto.py capture")
    click.echo("  python otto.py answer [Q_ID]     (Q_ID is optional)")
    click.echo("  python otto.py shell             (interactive text-command mode)")
    click.echo("  python otto.py help-menu")

    click.echo("\nFolder commands:")
    click.echo("  python otto.py list-folders")
    click.echo("  python otto.py current-folder")
    click.echo("  python otto.py create-folder [name]")
    click.echo("  python otto.py set-folder <name>")
    click.echo("  python otto.py cycle-folder")
    click.echo("  python otto.py rename-folder <old> <new>")

    click.echo("\nCapture management:")
    click.echo("  python otto.py list-questions [folder] [--limit N]   (--limit is optional)")
    click.echo("  python otto.py move-capture <Q_ID> <target-folder> [--create-target]")
    click.echo("  python otto.py delete-capture <Q_ID> [--yes]")
    click.echo("  python otto.py delete-folder <name> [--move-to X | --force] [--yes]")

    click.echo("\nSettings:")
    click.echo("  python otto.py settings-show")
    click.echo("  python otto.py settings-set <clear_on_capture|clear_on_answer> <true|false>")
    click.echo("  python otto.py show-model-fallbacks")

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

    try:
        import sys
        import termios
        termios.tcflush(sys.stdin, termios.TCIFLUSH)
    except Exception:
        pass


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


@cli.command(name="show-model-fallbacks")
def show_model_fallbacks_cmd():
    fallbacks = get_model_fallbacks()
    click.echo(click.style("Model fallbacks (in order):", fg='cyan', bold=True))
    for index, model_name in enumerate(fallbacks, start=1):
        click.echo(f"  {index}. {model_name}")


@cli.command(name="settings-show")
def settings_show_cmd():
    click.echo(click.style("Settings:", fg='cyan', bold=True))
    click.echo(f"  clear_on_capture = {get_setting('clear_on_capture', 'true')}")
    click.echo(f"  clear_on_answer  = {get_setting('clear_on_answer', 'false')}")


@cli.command(name="settings-set")
@click.argument("key")
@click.argument("value")
def settings_set_cmd(key, value):
    normalized_key = str(key or "").strip().lower()
    allowed = {"clear_on_capture", "clear_on_answer"}
    if normalized_key not in allowed:
        click.echo(click.style(
            "Unsupported setting key. Use clear_on_capture or clear_on_answer.",
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


@cli.command(name="shell")
def shell_cmd():
    click.echo(click.style("Interactive mode. Type 'help' for menu, 'exit' to quit.", fg='cyan', bold=True))
    while True:
        try:
            raw = input("otto> ").strip()
        except (EOFError, KeyboardInterrupt):
            click.echo("\nExiting shell.")
            return

        if not raw:
            continue

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

        try:
            cli.main(args=args, prog_name="otto.py", standalone_mode=False)
        except SystemExit:
            continue
        except click.ClickException as error:
            error.show()
        except Exception as error:
            click.echo(click.style(f"Command error: {error}", fg='red'))


@cli.command(name="set-folder")
@click.argument("folder_name")
def set_folder_cmd(folder_name):
    folder = set_active_folder(folder_name, create_if_missing=False)
    if not folder:
        click.echo(click.style(f"Folder does not exist: {folder_name}", fg='red', bold=True))
        click.echo("Use create-folder first, then set-folder.")
        return
    click.echo(click.style(f"Active folder set to: {folder}", fg='green', bold=True))


@cli.command(name="create-folder")
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


@cli.command(name="rename-folder")
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


@cli.command(name="current-folder")
def current_folder_cmd():
    folder = get_active_folder()
    click.echo(click.style(f"Current folder: {folder}", fg='blue', bold=True))


@cli.command(name="list-folders")
def list_folders_cmd():
    _print_folders_table()


def _print_folders_table():
    active = get_active_folder()
    folders = list_folders_with_counts()
    if not folders:
        click.echo("No folders found.")
        return

    names = [folder["name"] for folder in folders]
    next_name = None
    if names:
        active_idx = names.index(active) if active in names else -1
        if active_idx >= 0:
            next_name = names[(active_idx + 1) % len(names)]

    click.echo(click.style("Folders:", fg='cyan', bold=True))
    click.echo("STATUS    NAME                 COUNT")
    click.echo("--------  -------------------  -----")
    for folder in folders:
        folder_name = folder["name"]
        status = ""
        line = f"{folder_name:<19}  {folder['count']:>5}"
        if folder_name == active:
            status = "ACTIVE"
            click.echo(click.style(f"{status:<8}  {line}", fg='green', bold=True))
        elif folder_name == next_name:
            status = "NEXT"
            click.echo(click.style(f"{status:<8}  {line}", fg='yellow'))
        else:
            click.echo(f"{'':<8}  {line}")


@cli.command(name="list-questions")
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


@cli.command(name="move-capture")
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


@cli.command(name="delete-capture")
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


@cli.command(name="delete-folder")
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


@cli.command(name="cycle-folder")
def cycle_folder_cmd():
    next_folder = cycle_active_folder()
    click.echo(click.style(f"Active folder switched to: {next_folder}", fg='green', bold=True))
    _print_folders_table()

@cli.command()
def capture():
    raw_response = capture_and_interpret()
    
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
        _display_confidence_reasons(question.confidence_reasons)
        
        # 3. Question
        click.echo(click.style(f"\nQ: {question.question_text}", bold=True))
        
        # 4. Context 
        click.echo("_" * 50)
        click.echo(click.style("CONTEXT:", fg='cyan', underline=True))
        click.echo(question.context)
        click.echo("_" * 50)
        click.echo(f"Press Alt+Shift+A to reveal solution.")
        click.echo("Press Alt+Shift+F to show folder list.")
        click.echo("Press Alt+Shift+R to rotate folder.")
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
    _display_confidence_reasons(confidence_reasons)

    _display_answer(question_type, ans, answer_payload, mapping, options)

if __name__ == "__main__":
    init_db()
    cli()