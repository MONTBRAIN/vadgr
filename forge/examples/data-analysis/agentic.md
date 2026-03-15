# Data Analysis Pipeline, Workflow Orchestrator

## Trigger Commands

- `analyze a dataset`
- `start data analysis`
- `/start-analysis`

---

## Workflow Overview

```
Step 1         Step 2          Step 3          Step 4          Step 5          Step 6
Discover  -->  Profile     -->  Design     -->  Run        -->  Generate   -->  Review &
Data           Data             Analysis        Analysis        Report          Deliver
               ⏸               ⏸                                              ⏸
```

---

## Step 1: Discover Data

**Step file:** `agent/steps/step_01_discover-data.md`

Read the step file and execute it. Interview the user to establish the dataset, analysis questions, and target audience. Validate the dataset is accessible and compile a dataset brief for confirmation.

**Save:** `tasks/{date}/{id}/01_dataset_info.md`

---

## Step 2: Profile Data ⏸

**Step file:** `agent/steps/step_02_profile-data.md`

Read the step file and execute it. Set up the Python environment, run the profiling script, and interpret the results using the Data Profiler prompt. Present the profile summary for approval.

**Save:** `tasks/{date}/{id}/02_profile.md`

---

## Step 3: Design Analysis ⏸

**Step file:** `agent/steps/step_03_design-analysis.md`

Read the step file and execute it. Design metrics, charts, and statistical tests for each user question using the Analysis Architect prompt. Present the analysis plan for approval.

**Save:** `tasks/{date}/{id}/03_analysis_plan.md`

---

## Step 4: Run Analysis

**Step file:** `agent/steps/step_04_run-analysis.md`

Read the step file and execute it. Copy the analysis template, customize it per the approved plan, execute it, and verify all expected outputs were generated.

**Save:** Analysis outputs in `tasks/{date}/{id}/output/`

---

## Step 5: Generate Report

**Step file:** `agent/steps/step_05_generate-report.md`

Read the step file and execute it. Run the report generation script, then enhance the report with executive summary, methodology, findings, conclusions, and limitations using the Report Writer prompt.

**Save:** `tasks/{date}/{id}/report.md`

---

## Step 6: Review & Deliver ⏸

**Step file:** `agent/steps/step_06_review-deliver.md`

Read the step file and execute it. Run the self-review checklist, present the final report and delivery summary, and wait for user approval.

**Save:** Final delivery in `tasks/{date}/{id}/`

---

## After Each Step

**ALWAYS ask for user approval before saving/marking complete:**

1. Show output to the user
2. Ask: "Does this look good? Any changes needed?"
3. **Wait for user approval**
   - If changes requested: modify and show again
   - If approved: continue
4. Save files
5. Confirm: "Saved"

**NEVER proceed to the next step without user confirmation.**

---

## Output Structure

```
tasks/YYYY-MM-DD/{id}/
├── TASK_INFO.md              # Progress tracker
├── 01_dataset_info.md        # Dataset description
├── 02_profile.md             # Profiling results
├── 03_analysis_plan.md       # Approved analysis design
├── analysis.py               # Customized analysis script
├── requirements.txt          # From template
├── output/                   # Generated charts and data
│   ├── summary_stats.csv
│   ├── chart_1.png
│   └── chart_N.png
└── report.md                 # Final compiled report
```

---

## Quality Checks

| Step | Check |
|------|-------|
| 01 | Dataset path valid? Questions listed? Audience defined? User confirmed? |
| 02 | Profiling script ran successfully? All columns profiled? Quality issues flagged? User approved? |
| 03 | Every question mapped to a metric or chart? Chart types match data types? No more than 8 charts? User approved? |
| 04 | Analysis script ran without errors? All expected outputs generated? CSVs and PNGs present? |
| 05 | Report has executive summary, methodology, findings, conclusions, limitations? All charts embedded? |
| 06 | Self-review checklist passed? All questions answered? No placeholders? User approved final delivery? |
