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
    raw_response = capture_and_interpret()
    
    try:
        data = json.loads(raw_response)
        
        if "error" in data:
            click.echo(click.style(f"❌ AI Error: {data.get('details', 'Unknown')}", fg='red'))
            return

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
        
        # --- DISPLAY OUTPUT ---
        click.clear()
        
        # 1. Header
        click.echo(click.style(f"[{question.classification}] ID: {q_id}", fg='blue', bold=True))
        
        # 2. Confidence Score (Purple/Magenta) - High Visibility at top
        conf_percent = int(question.confidence * 100)
        click.echo(click.style(f"AI Confidence: {conf_percent}%", fg='magenta', bold=True))
        
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

    # Indices: id=0, answer=6, mapping=7, confidence=8
    display_id, ans, mapping_str, conf = row[0], row[6], row[7], row[8]
    
    # --- DISPLAY SOLUTION ---
    click.echo(click.style(f"\n💡 SOLUTION [{display_id}]", fg='green', bold=True))
    
    # Confidence Score (Purple/Magenta)
    click.echo(click.style(f"AI Confidence: {int(conf * 100)}%", fg='magenta', bold=True))

    if ans and ans != "null":
        click.echo(f"\nAnswer: {ans}")
    
    if mapping_str and mapping_str != "null":
        try:
            mapping = json.loads(mapping_str)
            for key, val in mapping.items():
                click.echo(click.style(f"\n{key}:", bold=True))
                if isinstance(val, list):
                    for item in val: # Corrected variable name
                         click.echo(f"  - {item}")
                else:
                    click.echo(f"  - {val}")
        except:
            pass 

if __name__ == "__main__":
    init_db()
    cli()