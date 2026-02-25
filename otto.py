import click
import json
import uuid
from vision import capture_and_interpret
from database import init_db, save_question, get_question, get_latest_question
from models import OttoQuestion


QUESTION_TYPE_LABELS = {
    "MULTIPLE_CHOICE": "Multiple Choice",
    "TRUE_FALSE": "True/False",
    "FILL_IN_THE_BLANK": "Fill In The Blank",
    "CATEGORIZATION": "Categorization",
    "SHORT_ANSWER": "Short Answer",
    "OTHER": "Other"
}


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


def _normalize_question_type(raw_type, fallback_classification):
    value = str(raw_type or fallback_classification or "").strip().lower().replace("-", " ").replace("_", " ")

    if "categor" in value:
        return "CATEGORIZATION"
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

    if question_type in {"MULTIPLE_CHOICE", "TRUE_FALSE"} and len(options) < 2:
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

    if answer_text:
        click.echo(f"\nAnswer: {answer_text}")

@click.group()
def cli():
    pass

@cli.command()
def capture():
    raw_response = capture_and_interpret()
    
    try:
        data = _parse_json_response(raw_response)
        
        if "error" in data:
            click.echo(click.style(f"❌ AI Error: {data.get('details', 'Unknown')}", fg='red'))
            return

        q_id = str(uuid.uuid4())[:5].upper()
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
            path="general",
            question_text=data.get('question_text', 'No text found'),
            question_type=question_type,
            classification=QUESTION_TYPE_LABELS.get(question_type, data.get('classification', 'Unknown')),
            options=options,
            context=data.get('context', 'No context available'),
            answer=answer_text,
            suggested_mapping=suggested_mapping,
            answer_payload=answer_payload,
            confidence=calibrated_confidence,
            confidence_reasons=confidence_reasons
        )
        
        save_question(question)
        
        # --- DISPLAY OUTPUT ---
        click.clear()
        
        # 1. Header
        click.echo(click.style(f"[{question.classification}] ID: {q_id}", fg='blue', bold=True))
        
        # 2. Confidence Score (Purple/Magenta) - High Visibility at top
        conf_percent = int(question.confidence * 100)
        click.echo(click.style(f"AI Confidence: {conf_percent}%", fg='magenta', bold=True))
        _display_confidence_reasons(question.confidence_reasons)
        
        # 3. Question
        click.echo(click.style(f"\nQ: {question.question_text}", bold=True))
        
        # 4. Context 
        click.echo("_" * 50)
        click.echo(click.style("CONTEXT:", fg='cyan', underline=True))
        click.echo(question.context)
        click.echo("_" * 50)
        click.echo(f"Press Alt+Shift+A to reveal solution.")
        
    except Exception as e:
        click.echo(f"Processing error: {e}")

@cli.command()
@click.argument('q_id', required=False)
def answer(q_id):
    row = get_question(q_id.upper()) if q_id else get_latest_question()

    if not row:
        click.echo("No question found.")
        return

    display_id = row.get("id")
    ans = row.get("answer")
    mapping_str = row.get("suggested_mapping")
    options_str = row.get("options")
    payload_str = row.get("answer_payload")
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
    
    # Confidence Score (Purple/Magenta)
    click.echo(click.style(f"AI Confidence: {int(conf * 100)}%", fg='magenta', bold=True))
    _display_confidence_reasons(confidence_reasons)

    _display_answer(question_type, ans, answer_payload, mapping, options)

if __name__ == "__main__":
    init_db()
    cli()