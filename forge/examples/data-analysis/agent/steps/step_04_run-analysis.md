# Step 4: Run Analysis

**Purpose:** Generate and execute the analysis scripts.

**Prompt:** None (script generation and execution step)

---

## Inputs
- Approved analysis plan from Step 3: `tasks/{date}/{id}/03_analysis_plan.md`
- Dataset path from Step 1: `tasks/{date}/{id}/01_dataset_info.md`

---

## Workflow

1. Create the task output directory:
   ```
   mkdir -p tasks/{date}/{id}/output
   ```

2. Copy the analysis template to the task folder:
   ```
   cp agent/utils/analysis-template/analysis.py tasks/{date}/{id}/analysis.py
   cp agent/utils/analysis-template/requirements.txt tasks/{date}/{id}/requirements.txt
   ```

3. Customize `tasks/{date}/{id}/analysis.py` based on the approved analysis plan:
   - Update `load_data()` with the actual dataset path
   - Implement `compute_metrics()` with the specific metrics from the plan
   - Implement `generate_charts()` with the specific charts from the plan
   - Add any additional functions needed for statistical tests

4. Run the analysis:
   ```
   source agent/scripts/.venv/bin/activate
   cd tasks/{date}/{id}
   python analysis.py
   ```

5. Verify outputs were generated:
   - Check `output/` directory for expected CSV and PNG files
   - Verify `summary_stats.csv` exists
   - Verify all planned charts were generated
   - Report any errors or missing outputs

---

## Required Outputs

### Agent Output (inter-step context)
Save to: `tasks/{date}/{id}/output/`
- `summary_stats.csv` - computed metrics
- `chart_1.png` through `chart_N.png` - generated charts
- Any additional CSV files from statistical tests

### User Output (deliverables)
Save to: `tasks/{date}/{id}/output/`
- All generated charts and data files

---

## Quality Check

- Analysis script ran without errors?
- summary_stats.csv present?
- All planned charts generated?
- Output directory contains expected files?
