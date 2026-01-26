import click
import json
import uuid
from vision import capture_and_interpret
from database import init_db, save_question, get_question, get_latest_question
from models import OttoQuestion

@click.group()
def cli():
    pass

@cli.command()
def capture():
    click.echo("Running capture...")
    raw_response = capture_and_interpret()
    
    try:
        data = json.loads(raw_response)
        q_id = str(uuid.uuid4())[:5].upper()
        
        question = OttoQuestion(
            id=q_id,
            path="general",
            question_text=data.get('question_text', 'No text found'),
            classification=data.get('classification', 'Unknown'),
            options=data.get('options', []),
            context=data.get('context', 'No context available'),
            answer=data.get('answer'),
            suggested_mapping=data.get('suggested_mapping'),
            confidence=data.get('confidence', 0.0)
        )
        
        save_question(question)
        
        click.echo(f"Stored as ID: {q_id}")
        click.echo(f"Type: {question.classification}")
        click.echo(f"Question: {question.question_text}")
        click.echo("-" * 20)
        click.echo(f"STUDY HINT: {question.context}")
        # Added confidence score requirement
        click.echo(f"AI Confidence Score: {question.confidence}") 
        click.echo("-" * 20)
        click.echo(f"To see the answer, type: otto answer {q_id} or use Ctrl+Alt+A")

    except Exception as e:
        click.echo(f"Processing error: {e}")

@cli.command()
@click.argument('q_id', required=False)
def answer(q_id):
    if q_id:
        row = get_question(q_id.upper())
    else:
        row = get_latest_question()

    if not row:
        click.echo("No question found.")
        return

    # Data structure: answer index 6, mapping index 7, confidence index 8
    q_id_display = row[0]
    ans = row[6]
    mapping_str = row[7]
    conf = row[8]
    
    click.echo(f"Solution for {q_id_display}:")
    if ans and ans != "null":
        click.echo(f"Correct Answer: {ans}")
    
    if mapping_str:
        mapping = json.loads(mapping_str)
        if mapping:
            for key, val in mapping.items():
                click.echo(f"{key}: {val}")
    
    # Added confidence score requirement for answers
    click.echo("-" * 20)
    click.echo(f"AI Confidence Score: {conf}")
    click.echo("Reminder: AI can be wrong. Use this as a guide, not a definitive fact.")

if __name__ == "__main__":
    init_db()
    cli()