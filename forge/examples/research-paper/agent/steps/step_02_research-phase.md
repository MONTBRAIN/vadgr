# Step 2: Research Phase

**Purpose:** Find and evaluate authoritative sources for the paper.

**Prompt:** `agent/Prompts/01_Research_Analyst.md`

---

## Inputs
- Topic brief from Step 1: `output/{paper-name}/01_topic.md`

---

## Workflow

1. Review the topic brief from Step 1
2. Search the web for authoritative and academic sources on the topic
3. Evaluate each source for relevance, recency, and authority
4. Compile an annotated bibliography with 8-15 sources
5. For each source include: title, author, year, URL, 2-sentence annotation, relevance score (1-5)
6. Present the annotated bibliography to the user for review

**Wait for user approval. If changes requested, search for additional sources or remove weak ones.**

---

## Required Outputs

### Agent Output (inter-step context)
Save to: `output/{paper-name}/02_bibliography.md`
- Annotated bibliography with 8-15 sources
- Each source: title, author, year, URL, annotation, relevance score

### User Output (deliverables)
Save to: `output/{paper-name}/02_bibliography.md`
- The complete annotated bibliography document

---

## Quality Check

- At least 8 sources found?
- Every source has all 6 required fields (title, author, year, URL, annotation, relevance score)?
- Bibliography approved by user?
- Agent output file saved to the correct path?
