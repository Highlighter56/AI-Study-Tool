#!/usr/bin/env python3
"""Phase 4 CLI commands for otto.py - study-list, feedback-mark-quick, study-open"""

import click
import json
import os
import sys
import sqlite3
from database import (
    get_latest_study_run,
    get_study_questions,
    save_feedback,
    get_setting,
)


# External functions needed from otto.py (will be passed in)
_cli = None


def register_phase4_commands(cli):
    """Register Phase 4 commands with the Click CLI group"""
    global _cli
    _cli = cli
    cli.add_command(study_list_cmd)
    cli.add_command(feedback_mark_quick_cmd)
    cli.add_command(study_open_cmd)


@click.command(name="study-list")
@click.option("--run-id", "run_id", default="", help="Show questions from specific study run. Defaults to latest.")
@click.option("--limit", default=20, type=int, show_default=True, help="Max questions to show.")
@click.option("--debug", is_flag=True, default=False, help="Show scoring info for feedback ranking.")
def study_list_cmd(run_id, limit, debug):
    """List study questions from a run for quick reference and marking."""
    rid = str(run_id or "").strip()
    
    # If no run_id specified, use latest study run
    if not rid:
        latest = get_latest_study_run()
        if not latest:
            click.echo(click.style("No study runs found.", fg='yellow', bold=True))
            return
        rid = latest.get("id")
    
    # Validate run exists
    questions = get_study_questions(rid, limit=max(1, min(int(limit), 200)))
    if not questions:
        click.echo(click.style(f"No questions found in study run {rid}.", fg='yellow', bold=True))
        return
    
    # Get run metadata
    conn = sqlite3.connect("otto.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM study_runs WHERE id = ?", (rid,))
    row = cursor.fetchone()
    run = dict(row) if row else {}
    conn.close()
    
    # Format and display
    title = run.get("title", "Study Material")
    created = run.get("created_at", "unknown")
    model = run.get("model_used", "unknown")
    click.echo(click.style(f"Study Run: {rid}", fg='cyan', bold=True))
    click.echo(f"  Title: {title}")
    click.echo(f"  Model: {model}")
    click.echo(f"  Created: {created}")
    click.echo(f"  Questions ({len(questions)}):")
    
    for q in questions:
        q_id = q.get("id", "")
        pos = q.get("position", 0)
        q_type = q.get("question_type", "")
        q_text = str(q.get("question_text", ""))[:60]
        click.echo(f"    [{pos}] Q{pos} [{q_id}] ({q_type}): {q_text}...")
        if debug:
            explanation = q.get("explanation", "")
            if explanation:
                click.echo(f"         Explanation: {str(explanation)[:70]}...")


@click.command(name="feedback-mark-quick")
@click.argument("run_id")
@click.argument("question_num", type=int)
@click.option("--status", type=click.Choice(["correct", "incorrect", "unverified"], case_sensitive=False), required=True, help="Mark as...")
@click.option("--wrong", default="", help="What was wrong (for incorrect status).")
@click.option("--correct", default="", help="What the correct answer/approach is.")
@click.option("--note", default="", help="General note for context.")
def feedback_mark_quick_cmd(run_id, question_num, status, wrong, correct, note):
    """Quick feedback marking by question number within a study run."""
    rid = str(run_id or "").strip().upper()
    qnum = int(question_num or 0)
    
    if qnum < 1:
        click.echo(click.style("Question number must be >= 1.", fg='red', bold=True))
        return
    
    # Get all questions from this run
    questions = get_study_questions(rid, limit=500)
    if not questions:
        click.echo(click.style(f"No questions in study run {rid}.", fg='red', bold=True))
        return
    
    # Find question by position
    matching = [q for q in questions if q.get("position") == qnum]
    if not matching:
        click.echo(click.style(f"Question #{qnum} not found in run {rid}. Valid range: 1-{len(questions)}", fg='red', bold=True))
        return
    
    q = matching[0]
    q_id = q.get("id")
    result = save_feedback("study", q_id, status, corrected_answer=correct or wrong, note=note or "")
    
    if not result.get("ok"):
        click.echo(click.style(f"Error: {result.get('reason')}", fg='red', bold=True))
        return
    
    click.echo(click.style(f"Feedback saved for Q{qnum}.", fg='green', bold=True))
    click.echo(f"Target: {result.get('target_type')}:{result.get('target_id')} | Status: {result.get('status')}")


@click.command(name="study-open")
@click.argument("run_id", required=False)
def study_open_cmd(run_id):
    """Open the first output file from a study run."""
    rid = str(run_id or "").strip()
    if not rid:
        latest = get_latest_study_run()
        if not latest:
            click.echo(click.style("No study runs found.", fg='yellow', bold=True))
            return
        rid = latest.get("id")
    
    conn = sqlite3.connect("otto.db")
    cursor = conn.cursor()
    cursor.execute("SELECT output_files FROM study_runs WHERE id = ?", (rid,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        click.echo(click.style(f"Study run {rid} not found.", fg='red', bold=True))
        return
    
    output_files_json = row[0]
    try:
        output_files = json.loads(output_files_json or "[]")
    except Exception:
        output_files = []
    
    if not output_files:
        click.echo(click.style(f"No output files for study run {rid}.", fg='yellow', bold=True))
        return
    
    first_file = output_files[0]
    if not os.path.exists(first_file):
        click.echo(click.style(f"File not found: {first_file}", fg='red', bold=True))
        return
    
    click.echo(click.style(f"Opening: {first_file}", fg='green'))
    if sys.platform == "win32":
        os.startfile(first_file)
    elif sys.platform == "darwin":
        os.system(f"open '{first_file}'")
    else:
        os.system(f"xdg-open '{first_file}'")
