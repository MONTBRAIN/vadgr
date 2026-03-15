# Step 5: Generate Report

**Purpose:** Compile analysis outputs into a structured markdown report.

**Prompt:** `agent/Prompts/03_Report_Writer.md`

---

## Inputs
- Analysis outputs from Step 4: `tasks/{date}/{id}/output/`
- Analysis plan from Step 3: `tasks/{date}/{id}/03_analysis_plan.md`
- Dataset info from Step 1: `tasks/{date}/{id}/01_dataset_info.md`
- Profiling results from Step 2: `tasks/{date}/{id}/02_profile.md`

---

## Workflow

1. Run the report generation script:
   ```
   source agent/scripts/.venv/bin/activate
   python agent/scripts/generate_report.py tasks/{date}/{id}
   ```

2. Review the generated report skeleton
3. Enhance the report following the Report Writer prompt:
   - Write an executive summary readable by non-technical audiences
   - Write a methodology section explaining the approach
   - For each user question, write a findings section with:
     - Specific numbers and context (not just raw values)
     - Embedded charts with descriptive captions
     - Clear interpretation of what the data shows
   - Write conclusions tying findings back to the original questions
   - Write a limitations section noting caveats and data quality issues
4. Finalize the report

---

## Required Outputs

### Agent Output (inter-step context)
Save to: `tasks/{date}/{id}/report.md`
- Complete markdown report with all sections

### User Output (deliverables)
Save to: `tasks/{date}/{id}/report.md`
- Final report with: executive summary, methodology, findings (per question), conclusions, limitations
- All charts embedded with descriptive captions

---

## Quality Check

- Every user question has a corresponding findings section?
- Every chart embedded with a descriptive caption?
- Executive summary readable by a non-technical audience?
- Limitations section present?
- Agent output file saved to the correct path?
