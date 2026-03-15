# Step 6: Review and Deliver

**Purpose:** Final quality review and delivery of all outputs.

**Prompt:** None (review and delivery step)

---

## Inputs
- All previous step outputs:
  - `tasks/{date}/{id}/01_dataset_info.md`
  - `tasks/{date}/{id}/02_profile.md`
  - `tasks/{date}/{id}/03_analysis_plan.md`
  - `tasks/{date}/{id}/output/` (charts and data)
  - `tasks/{date}/{id}/report.md`

---

## Workflow

1. Run the self-review checklist:
   - [ ] Every user question has a corresponding finding in the report
   - [ ] Every chart has a caption explaining what it shows
   - [ ] Every finding references specific numbers with context
   - [ ] Executive summary is readable by a non-technical audience
   - [ ] Limitations section is present and honest
   - [ ] All file paths in the report are correct
   - [ ] No broken image references
   - [ ] No placeholder text remaining

2. Present the report to the user

3. Present the final delivery summary:
   ```
   Analysis: {task_id}
   Dataset: {dataset_name}
   Questions answered: {count}
   Charts generated: {count}
   Report: tasks/{date}/{id}/report.md

   Files:
   tasks/{date}/{id}/
   ├── TASK_INFO.md
   ├── 01_dataset_info.md
   ├── 02_profile.md
   ├── 03_analysis_plan.md
   ├── analysis.py
   ├── requirements.txt
   ├── output/
   │   ├── summary_stats.csv
   │   ├── chart_1.png
   │   └── ...
   └── report.md
   ```

**Wait for user approval. If changes requested, revise and re-deliver.**

---

## Required Outputs

### Agent Output (inter-step context)
Save to: `tasks/{date}/{id}/TASK_INFO.md`
- Self-review checklist results (all items passed)
- Final delivery summary

### User Output (deliverables)
Save to: `tasks/{date}/{id}/`
- All files listed in the delivery summary
- Completed report at `tasks/{date}/{id}/report.md`

---

## Quality Check

- Self-review checklist passes all items?
- No placeholder text remaining in the report?
- All chart image references valid?
- Delivery summary presented to user?
- User approval received?
