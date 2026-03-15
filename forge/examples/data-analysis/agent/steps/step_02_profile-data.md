# Step 2: Profile Data

**Purpose:** Run automated profiling and interpret the results.

**Prompt:** `agent/Prompts/01_Data_Profiler.md`

---

## Inputs
- Dataset path and user questions from Step 1
- Previous step context: `tasks/{date}/{id}/01_dataset_info.md`

---

## Workflow

1. Ensure the Python environment is set up:
   ```
   python3 -m venv agent/scripts/.venv && source agent/scripts/.venv/bin/activate && pip install -r agent/scripts/requirements.txt
   ```
   (Skip if `agent/scripts/.venv` already exists.)

2. Run the profiling script against the dataset:
   ```
   source agent/scripts/.venv/bin/activate
   python agent/scripts/profile_data.py <path_to_dataset>
   ```

3. Capture the profiling output
4. Interpret the results using the Data Profiler prompt:
   - Identify data quality issues (missing values, type mismatches)
   - Highlight interesting distributions and patterns
   - Recommend cleaning steps if needed
   - Flag if the dataset is too small for statistical significance
5. Present the interpreted profile summary to the user

**Wait for user approval. If changes requested, re-run profiling with adjustments or address concerns.**

---

## Required Outputs

### Agent Output (inter-step context)
Save to: `tasks/{date}/{id}/02_profile.md`
- Column-level statistics (type, nulls, unique values, distributions)
- Data quality issues found
- Interesting patterns and distributions
- Recommended cleaning steps
- Statistical significance assessment

### User Output (deliverables)
Save to: `tasks/{date}/{id}/02_profile.md`
- The interpreted profiling summary document

---

## Quality Check

- Profiling script ran successfully?
- All columns profiled?
- Quality issues identified and reported?
- Profile summary approved by user?
- Agent output file saved to the correct path?
