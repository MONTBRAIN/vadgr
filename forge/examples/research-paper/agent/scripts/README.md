# Scripts

Scripts that support the research paper workflow.

## Structure

- `src/` - Source scripts
- `tests/` - Test scripts

## Setup

Create and activate a Python virtual environment before running any scripts:

```bash
python3 -m venv agent/scripts/.venv
source agent/scripts/.venv/bin/activate
pip install -r agent/scripts/requirements.txt
```

Run this from the project root (`research-paper/`). The venv lives inside `agent/scripts/.venv` to keep it co-located.

## Usage

All scripts in `src/` should be run with the venv active:

```bash
source agent/scripts/.venv/bin/activate
python agent/scripts/src/your_script.py
```

## Tests

```bash
source agent/scripts/.venv/bin/activate
python -m pytest agent/scripts/tests/
```
