# Step 1: Topic Selection

**Purpose:** Establish the paper topic, target audience, scope, and desired length.

**Prompt:** None (interactive interview step)

---

## Inputs
- User's initial request to write a research paper
- No previous step context

---

## Workflow

**On trigger, ask ONE question at a time. Wait for each response.**

Question 1:
```
What topic should this research paper cover? Describe it in 2-3 sentences.
```

Question 2:
```
Who is the target audience? (e.g., "undergraduate students", "industry professionals",
"academic researchers in machine learning")
```

Question 3:
```
What is the scope of this paper? Should it be a broad survey, a focused deep-dive,
or a comparative analysis?
```

Question 4:
```
What is the desired length? (e.g., "short, 5 pages", "medium, 10-15 pages",
"long, 20+ pages")
```

**After all questions answered:** Compile a topic brief summarizing the topic, audience, scope, and length. Present it to the user for confirmation.

---

## Required Outputs

### Agent Output (inter-step context)
Save to: `output/{paper-name}/01_topic.md`
- Topic description
- Target audience
- Scope (survey, deep-dive, or comparative)
- Desired length
- User confirmation status

### User Output (deliverables)
Save to: `output/{paper-name}/01_topic.md`
- The compiled topic brief document

---

## Quality Check

- All four questions answered?
- Topic brief confirmed by user?
- Agent output file saved to the correct path?
