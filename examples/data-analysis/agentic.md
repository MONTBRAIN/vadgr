# Data Analysis Pipeline — Workflow Orchestrator

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

**Purpose:** Establish what dataset to analyze, what questions to answer, and who the report is for.

**On trigger, ask ONE question at a time. Wait for each response.**

Question 1:
```
What dataset should I analyze? Provide a file path or URL to a CSV file.
```

Question 2:
```
What questions do you want answered from this data? List 2-5 specific questions.
(e.g., "What are the top-selling products?", "Is there a seasonal trend in revenue?")
```

Question 3:
```
Who is the target audience for the report?
(e.g., "executive team", "engineering managers", "marketing analysts")
```

**After all questions answered:**

1. Validate the dataset exists and is readable:
   - If file path: check the file exists and can be opened
   - If URL: attempt to download and verify it is a valid CSV
2. Report: file name, file size, first 5 rows preview
3. Compile a dataset brief summarizing the file, questions, and audience
4. Present the brief for confirmation

**Save:** `tasks/{date}/{id}/01_dataset_info.md`

---

## Step 2: Profile Data ⏸

**Purpose:** Run automated profiling and interpret the results.

**Read:** `Prompts/1. Data Profiler.md`

**Workflow:**

1. Ensure the Python environment is set up:
   ```
   python3 -m venv scripts/.venv && source scripts/.venv/bin/activate && pip install -r scripts/requirements.txt
   ```
   (Skip if `.venv` already exists.)

2. Run the profiling script against the dataset:
   ```
   source scripts/.venv/bin/activate
   python scripts/profile_data.py <path_to_dataset>
   ```

3. Capture the profiling output
4. Interpret the results using the Data Profiler prompt:
   - Identify data quality issues (missing values, type mismatches)
   - Highlight interesting distributions and patterns
   - Recommend cleaning steps if needed
   - Flag if the dataset is too small for statistical significance
5. Present the interpreted profile summary to the user

**Wait for user approval. If changes requested, re-run profiling with adjustments or address concerns.**

**Save:** `tasks/{date}/{id}/02_profile.md`

---

## Step 3: Design Analysis ⏸

**Purpose:** Design the analysis plan based on profiling results and user questions.

**Read:** `Prompts/2. Analysis Architect.md`

**Workflow:**

1. Review the dataset info from Step 1 and profiling results from Step 2
2. Review the user's original questions
3. For each question, design:
   - **Metrics to compute** — name, formula or method, rationale for why this metric answers the question
   - **Charts to generate** — chart type, x-axis, y-axis, purpose. Match chart type to data type:
     - Categorical data: bar chart, pie chart
     - Continuous data: histogram, scatter plot, box plot
     - Time series: line chart
     - Relationships: scatter plot, heatmap
   - **Statistical tests** — if applicable (correlation, t-test, chi-square, etc.)
4. Compile the analysis plan with expected insights
5. Present the plan for approval

**Constraints:**
- Every user question must map to at least one metric or chart
- No more than 8 charts total
- At least one summary statistics table
- Prioritize answering user's questions over exploratory analysis

**Wait for user approval. If changes requested, revise the plan.**

**Save:** `tasks/{date}/{id}/03_analysis_plan.md`

---

## Step 4: Run Analysis

**Purpose:** Generate and execute the analysis scripts.

**Workflow:**

1. Create the task output directory:
   ```
   mkdir -p tasks/{date}/{id}/output
   ```

2. Copy the analysis template to the task folder:
   ```
   cp utils/analysis-template/analysis.py tasks/{date}/{id}/analysis.py
   cp utils/analysis-template/requirements.txt tasks/{date}/{id}/requirements.txt
   ```

3. Customize `tasks/{date}/{id}/analysis.py` based on the approved analysis plan:
   - Update `load_data()` with the actual dataset path
   - Implement `compute_metrics()` with the specific metrics from the plan
   - Implement `generate_charts()` with the specific charts from the plan
   - Add any additional functions needed for statistical tests

4. Run the analysis:
   ```
   source scripts/.venv/bin/activate
   cd tasks/{date}/{id}
   python analysis.py
   ```

5. Verify outputs were generated:
   - Check `output/` directory for expected CSV and PNG files
   - Verify `summary_stats.csv` exists
   - Verify all planned charts were generated
   - Report any errors or missing outputs

**Save:** Analysis outputs in `tasks/{date}/{id}/output/`

---

## Step 5: Generate Report

**Purpose:** Compile analysis outputs into a structured markdown report.

**Read:** `Prompts/3. Report Writer.md`

**Workflow:**

1. Run the report generation script:
   ```
   source scripts/.venv/bin/activate
   python scripts/generate_report.py tasks/{date}/{id}
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
4. Finalize `tasks/{date}/{id}/report.md`

**Save:** `tasks/{date}/{id}/report.md`

---

## Step 6: Review & Deliver ⏸

**Purpose:** Final quality review and delivery of all outputs.

**Workflow:**

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
