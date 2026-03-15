# Step 1: Discover Data

**Purpose:** Establish what dataset to analyze, what questions to answer, and who the report is for.

**Prompt:** None (interactive interview step)

---

## Inputs
- User's initial request to analyze a dataset
- No previous step context

---

## Workflow

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

---

## Required Outputs

### Agent Output (inter-step context)
Save to: `tasks/{date}/{id}/01_dataset_info.md`
- Dataset path or URL
- File name, size, row/column counts
- First 5 rows preview
- User's questions (numbered list)
- Target audience
- User confirmation status

### User Output (deliverables)
Save to: `tasks/{date}/{id}/01_dataset_info.md`
- The compiled dataset brief document

---

## Quality Check

- All three questions answered?
- Dataset exists and is readable?
- Dataset brief confirmed by user?
- Agent output file saved to the correct path?
