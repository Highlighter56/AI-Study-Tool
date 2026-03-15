# AI-Study-Tool

AI-Study-Tool captures on-screen questions, sends them to Gemini for structured interpretation, stores results in SQLite, and helps you review answers with confidence notes.

## What It Does

- Captures a screenshot and extracts:
	- question text
	- question type/classification
	- answer options (when present)
	- context paragraph
	- normalized answer payload
	- confidence + confidence notes
	- model used
- Stores all captures in `otto.db`.
- Supports folder-based organization with an active folder.
- Supports both hotkey mode (`listener.py`) and text command mode (`otto.py`, including interactive shell).

## Supported Question Types

- `MULTIPLE_CHOICE`
- `TRUE_FALSE`
- `FILL_IN_THE_BLANK`
- `CATEGORIZATION`
- `ORDERING`
- `SHORT_ANSWER`
- `OTHER` (fallback)

## Project Files

| File | Purpose |
| --- | --- |
| `listener.py` | Global hotkey listener mode |
| `otto.py` | CLI commands + interactive shell mode |
| `vision.py` | Screenshot + Gemini model fallback pipeline |
| `database.py` | SQLite schema and data operations |
| `models.py` | Pydantic model for stored question data |

## Requirements

- Python 3.10+
- A valid `GOOGLE_API_KEY`
- Windows is currently the primary tested OS

## Setup

1. Clone/pull this repository (or place these project files in one folder).
2. Create and activate a Python virtual environment.

Windows example:

```bash
python -m venv .venv
.venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create a `.env` file with:

```env
GOOGLE_API_KEY=your_key_here
```

## Run Modes

### 1) Hotkey Listener Mode

```bash
python listener.py
```

Hotkeys:

- `Alt+Shift+Q`: capture question/screen
- `Alt+Shift+A`: display answer for latest capture
- `Alt+Shift+K`: create folder
- `Alt+Shift+F`: show folders
- `Alt+Shift+R`: rotate active folder + show folders
- `Alt+Shift+H`: help menu
- `Alt+Shift+E`: exit listener

### 2) Text Command Mode

Run one-off commands:

```bash
python otto.py help-menu
```

### 3) Interactive Shell Mode

```bash
python otto.py shell
```

In shell mode, run commands without retyping `python otto.py ...`.

## Core Commands

```bash
python otto.py capture
python otto.py answer [Q_ID]
python otto.py help-menu
```

Notes:

- `capture` auto-copies the generated question ID to clipboard when possible.
- `answer` without `Q_ID` shows the latest capture.

## Folder Commands

```bash
python otto.py list-folders [--list]             # default is tree view; use --list for flat view
python otto.py current-folder
python otto.py create-folder [name]              # supports nested paths, e.g. unit1/section2
python otto.py set-folder <name>
python otto.py cycle-folder
python otto.py rename-folder <old> <new>
```

## Capture Management Commands

```bash
python otto.py list-questions [folder] [--limit N]
python otto.py move-capture <Q_ID> <target-folder> [--create-target]
python otto.py delete-capture <Q_ID> [--yes]
python otto.py delete-folder <name> [--move-to X | --force] [--yes]
```

## Settings

Show settings:

```bash
python otto.py settings-show
```

Set values:

```bash
python otto.py settings-set clear_on_capture true
python otto.py settings-set clear_on_answer false
python otto.py settings-set clear_on_folder_view true
python otto.py settings-set timeout_minutes 10
```

Current configurable settings:

| Setting | Description |
| --- | --- |
| `clear_on_capture` | Clear terminal before capture output |
| `clear_on_answer` | Clear terminal before answer output |
| `clear_on_folder_view` | Clear terminal before folder list/rotate output |
| `timeout_minutes` | Inactivity timeout for listener + shell (`5` to `30`) |
| `model_fallbacks` | Comma-separated fallback model list (managed by probe command) |

## Model Fallbacks

Show active fallback order:

```bash
python otto.py show-model-fallbacks
```

Probe model availability and optionally apply working models:

```bash
python otto.py probe-models
python otto.py probe-models --apply
python otto.py probe-models --models "modelA,modelB,modelC"  # example
```

`--models` accepts any comma-separated model names you want to test.

Fallback source priority:

1. `OTTO_MODEL_FALLBACKS` environment variable
2. `model_fallbacks` setting in SQLite
3. default fallback list in `vision.py`

## Data Storage

- SQLite DB: `otto.db`
- Screenshot file cache: `captures/last_capture.png` (latest capture only, overwritten each run)
- Persistent study data is stored as extracted/normalized text + metadata in SQLite

## Status

This project is actively evolving. Current implementation is stable for:

- capture + answer workflow
- folder-based organization
- model fallback tracking and probing
- settings-driven output/timeouts

Planned features include study-material generation by folder, richer review workflows, and additional capture controls.
