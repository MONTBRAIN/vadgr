# Step 6: Generate Scripts

**Purpose:** Generate workflow-specific scripts identified during architecture design and agent prompt writing.

**Prompt:** `forge/Prompts/06_Format_Script_Generator.md` or `forge/Prompts/07_Script_Generator.md`

---

## Inputs

- Architecture design from Step 2 (scripts identified during design)
- Step files from Step 5 (script requirements emitted via `## Script Requirements` sections)
- Scaffold created in Step 3 (write into existing directory)

---

## Workflow

**This step follows strict TDD. Tests are written FIRST. Implementation comes SECOND. No exceptions.**

**Every script must expose a `_cli()` function with argparse and end with `if __name__ == "__main__": _cli()`. CLI tests via subprocess are mandatory alongside API tests.**

1. **Collect script requirements** from two sources:
   - Scripts identified in Step 2's architecture design
   - `## Script Requirements` sections in step files generated in Step 5

   Merge and deduplicate. If both sources mention the same script, prefer the more detailed description.

2. If no scripts are needed, skip this step entirely. Not every workflow needs scripts.

3. For each **format script** (document/file generation -- PDF, HTML, XLSX, CSV, etc.):
   1. **Read:** `forge/Prompts/06_Format_Script_Generator.md`
   2. Read the CLI command from the `## Script Requirements` entry in the step file.
      The argparse interface must match that command exactly.
   3. Follow the prompt's TDD workflow strictly:
      - Design the public API (function signatures, data classes, style config)
      - Design the `_cli()` argparse interface to match the CLI command from the step file
      - Write the complete test file FIRST (at least 5 test methods plus at least 1 subprocess CLI test)
      - Write the implementation to make the tests pass
      - Run the tests -- ALL must pass before moving on
   3. Place via the scaffold CLI:

   ```bash
   python3 -m forge.scripts.src.scaffold add-script \
     --root output/{workflow-name} \
     --name gen_html.py \
     --script path/to/gen_html.py \
     --test path/to/test_gen_html.py \
     --deps jinja2 \
     --install
   ```

4. For each **general script** (API client, validator, scraper, data processor, etc.):
   1. **Read:** `forge/Prompts/07_Script_Generator.md`
   2. Read the CLI command from the `## Script Requirements` entry in the step file.
      The argparse interface must match that command exactly.
   3. Follow the prompt's TDD workflow strictly:
      - Design the public API
      - Design the `_cli()` argparse interface to match the CLI command from the step file
      - Write the complete test file FIRST (at least 3 test methods plus at least 1 subprocess CLI test; 5+ for complex scripts)
      - Write the implementation to make the tests pass
      - Run the tests -- ALL must pass before moving on
   4. Place via the scaffold CLI `add-script` command as above.

5. After ALL scripts are generated, run the full test suite:
   ```bash
   source agent/scripts/.venv/bin/activate
   python -m pytest agent/scripts/tests/ -v
   ```
   ALL tests must pass. If any test fails, fix the implementation (not the test) and re-run.

---

## Required Outputs

### Agent Output (inter-step context)

Held in context for subsequent steps. No file saved.
- Confirmation that all scripts were generated, placed, and tested

### User Output (deliverables)

Save to: `output/{workflow-name}/`
- `agent/scripts/src/{script_name}.py` for each script
- `agent/scripts/tests/test_{script_name}.py` for each script
- Updated `agent/scripts/requirements.txt` with new dependencies

---

## Quality Check

- All scripts from architecture and step file emissions generated?
- Each script has corresponding tests?
- Each script exposes a `_cli()` function with argparse and an `if __name__ == "__main__": _cli()` block?
- Each test file includes at least 1 subprocess test that calls the script via CLI?
- CLI argparse interface matches the command specified in the step file's Script Requirements?
- Dependencies added to requirements.txt?
- Tests pass?
- Scripts placed via scaffold CLI `add-script` (not manually)?
