# Scripts

Scripts that support the data analysis workflow.

## Structure

- `src/` - Source scripts
- `tests/` - Test scripts
- `profile_data.py` - Data profiling utility
- `generate_report.py` - Report generation utility

## Setup

Create and activate a Python virtual environment before running any scripts:

```bash
python3 -m venv agent/scripts/.venv
source agent/scripts/.venv/bin/activate
pip install -r agent/scripts/requirements.txt
```

Run this from the project root (`data-analysis/`). The venv lives inside `agent/scripts/.venv` to keep it co-located.

## Usage

All scripts in `src/` and the top-level utility scripts should be run with the venv active:

```bash
source agent/scripts/.venv/bin/activate
python agent/scripts/profile_data.py
python agent/scripts/generate_report.py
python agent/scripts/src/your_script.py
```

## Tests

```bash
source agent/scripts/.venv/bin/activate
python -m pytest agent/scripts/tests/
```
