# Scripts

Scripts that support the Agent Forge workflow.

## Structure

- `src/` - Source scripts
- `tests/` - Test scripts

## Setup

Create and activate a Python virtual environment before running any scripts:

```bash
python3 -m venv forge/scripts/.venv
source forge/scripts/.venv/bin/activate
pip install -r forge/scripts/requirements.txt
```

Run this from the project root (`Agent-Forge/`). The venv lives inside `forge/scripts/.venv` to keep it co-located.

## Usage

All scripts in `src/` should be run with the venv active:

```bash
source forge/scripts/.venv/bin/activate
python forge/scripts/src/your_script.py
```

## Tests

```bash
source forge/scripts/.venv/bin/activate
python -m pytest forge/scripts/tests/
```
