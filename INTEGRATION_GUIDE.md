# Phase 4 Integration Guide for otto.py

## Summary
Phase 4 database implementation is complete and fully tested. Three remaining integration points needed in otto.py:

## 1. Update _build_feedback_context_block (Line 474)

**Current implementation** (hardcoded settings):
```python
def _build_feedback_context_block(folder_name, question_type=None, limit=6, char_budget=1800):
    rows = get_feedback_for_prompt(folder_name, question_type=question_type, limit=limit)
    # ... rest of function
```

**Required update** (settings-aware):
```python
def _build_feedback_context_block(folder_name, question_type=None, limit=None, char_budget=None):
    """Build feedback context block respecting user settings."""
    # Read mode from settings
    mode = get_setting("feedback_context_mode", "full").strip().lower()
    if mode == "off":
        return ""  # Don't inject any feedback
    
    # Load limits from settings if not provided
    if limit is None:
        try:
            limit = int(get_setting("feedback_max_items", "6"))
        except (ValueError, TypeError):
            limit = 6
    
    if char_budget is None:
        try:
            char_budget = int(get_setting("feedback_char_budget", "1800"))
        except (ValueError, TypeError):
            char_budget = 1800
    
    # Apply light mode (reduce by 50%)
    if mode == "light":
        limit = max(1, limit // 2)
        char_budget = max(200, char_budget // 2)
    
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
            excluded_count = len(rows) - idx + 1
            if excluded_count > 0:
                lines.append(f"(... and {excluded_count} more excluded due to char budget)")
            break
        lines.append(text)
        used += len(text) + 1

    return "\n".join(lines).strip()
```

## 2. Update settings-show Command

**Add after line 1341** (after other settings display):
```python
# Around line 1345, after model_fallbacks display, add:
click.echo(click.style("\n  Feedback & Corrections:", fg='blue', bold=True))
click.echo(f"    {'feedback_context_mode':<20} = {get_setting('feedback_context_mode', 'full')}   (light|full|off)")
click.echo(f"    {'feedback_max_items':<20} = {get_setting('feedback_max_items', '6')}   (Max corrections)")
click.echo(f"    {'feedback_char_budget':<20} = {get_setting('feedback_char_budget', '1800')}   (Max chars)")
```

## 3. Update settings-set Command

**Add handling before line 1370** (before timeout_minutes):
```python
# Handle feedback_max_items
if normalized_key == "feedback_max_items":
    try:
        parsed_items = int(str(value).strip())
    except Exception:
        click.echo(click.style("feedback_max_items must be 1-20.", fg='red', bold=True))
        return
    if parsed_items < 1 or parsed_items > 20:
        click.echo(click.style("feedback_max_items must be between 1 and 20.", fg='red', bold=True))
        return
    saved = set_setting(normalized_key, str(parsed_items))
    click.echo(click.style(f"Updated {normalized_key} = {saved}", fg='green', bold=True))
    return

# Handle feedback_char_budget
if normalized_key == "feedback_char_budget":
    try:
        parsed_budget = int(str(value).strip())
    except Exception:
        click.echo(click.style("feedback_char_budget must be 200-5000.", fg='red', bold=True))
        return
    if parsed_budget < 200 or parsed_budget > 5000:
        click.echo(click.style("feedback_char_budget must be between 200 and 5000.", fg='red', bold=True))
        return
    saved = set_setting(normalized_key, str(parsed_budget))
    click.echo(click.style(f"Updated {normalized_key} = {saved}", fg='green', bold=True))
    return

# Handle feedback_context_mode
if normalized_key == "feedback_context_mode":
    normalized_value = str(value).strip().lower()
    if normalized_value not in {"light", "full", "off"}:
        click.echo(click.style("feedback_context_mode must be: light, full, or off", fg='red', bold=True))
        return
    saved = set_setting(normalized_key, normalized_value)
    click.echo(click.style(f"Updated {normalized_key} = {saved}", fg='green', bold=True))
    return
```

## Phase 4 Commands (Ready to Import)

File: `phase4_commands.py` (already created and compiled)

Commands available:
- `otto.py study-list [--run-id SR...] [--limit 20] [--debug]`
- `otto.py feedback-mark-quick SR... Q1 --status correct|incorrect|unverified [--wrong ...] [--correct ...] [--note ...]`
- `otto.py study-open [SR...]`

To integrate: Add to otto.py after Click CLI group definition:
```python
from phase4_commands import register_phase4_commands
# ... 
cli = click.group()
# ... after all commands defined:
register_phase4_commands(cli)
```

## Test Results

All Phase 4 core functionality tested and passing:
- Settings persistence and retrieval ✓
- Scoring calculation with metadata ✓
- Character budget enforcement ✓
- Token limits respected ✓

Test files:
- `test_phase4.py` - 2 test modules, basic validation
- `test_phase4_full.py` - 11 comprehensive tests (100% pass rate)

## Next Session

1. Apply the three updates above to otto.py
2. Import and register phase4_commands
3. Run `python otto.py settings-show` to verify feedback settings display
4. Test: `python otto.py settings-set feedback_context_mode light`
5. Generate study material and verify feedback context respects settings
6. Commit final otto.py integration
7. Create Phase 5 roadmap for analytics and refinements

## Impact

Users benefit from:
- Granular control over correction history injection
- Automatic relevance ranking of past mistakes
- Memory limits preventing token bloat
- Quick study material review and marking
- Persistent feedback loop learning system
