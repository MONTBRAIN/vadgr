# Step 3: Design Analysis

**Purpose:** Design the analysis plan based on profiling results and user questions.

**Prompt:** `agent/Prompts/02_Analysis_Architect.md`

---

## Inputs
- Dataset brief from Step 1: `tasks/{date}/{id}/01_dataset_info.md`
- Profiling results from Step 2: `tasks/{date}/{id}/02_profile.md`

---

## Workflow

1. Review the dataset info from Step 1 and profiling results from Step 2
2. Review the user's original questions
3. For each question, design:
   - **Metrics to compute** - name, formula or method, rationale for why this metric answers the question
   - **Charts to generate** - chart type, x-axis, y-axis, purpose. Match chart type to data type:
     - Categorical data: bar chart, pie chart
     - Continuous data: histogram, scatter plot, box plot
     - Time series: line chart
     - Relationships: scatter plot, heatmap
   - **Statistical tests** - if applicable (correlation, t-test, chi-square, etc.)
4. Compile the analysis plan with expected insights
5. Present the plan for approval

**Constraints:**
- Every user question must map to at least one metric or chart
- No more than 8 charts total
- At least one summary statistics table
- Prioritize answering user's questions over exploratory analysis

**Wait for user approval. If changes requested, revise the plan.**

---

## Required Outputs

### Agent Output (inter-step context)
Save to: `tasks/{date}/{id}/03_analysis_plan.md`
- Per-question breakdown: metrics, charts, statistical tests
- Chart specifications (type, axes, purpose)
- Expected insights and hypotheses

### User Output (deliverables)
Save to: `tasks/{date}/{id}/03_analysis_plan.md`
- The approved analysis plan document

---

## Quality Check

- Every user question mapped to at least one metric or chart?
- No more than 8 charts planned?
- At least one summary statistics table included?
- Analysis plan approved by user?
- Agent output file saved to the correct path?
