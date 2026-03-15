# Step 3: Outline Generation

**Purpose:** Create a structured outline with a clear thesis and section plan.

**Prompt:** `agent/Prompts/02_Outline_Architect.md`

---

## Inputs
- Topic brief: `output/{paper-name}/01_topic.md`
- Approved bibliography: `output/{paper-name}/02_bibliography.md`

---

## Workflow

1. Review the topic brief and approved bibliography
2. Identify major themes and arguments from the sources
3. Draft a thesis statement
4. Structure the paper into sections (Introduction, Body sections, Conclusion)
5. Write a 2-3 sentence summary for each section
6. Map specific sources to each section
7. Present the complete outline to the user for review

**Wait for user approval. If changes requested, revise structure or thesis.**

---

## Required Outputs

### Agent Output (inter-step context)
Save to: `output/{paper-name}/03_outline.md`
- Thesis statement
- Section structure with summaries
- Source-to-section mapping

### User Output (deliverables)
Save to: `output/{paper-name}/03_outline.md`
- The complete structured outline document

---

## Quality Check

- Thesis statement present?
- All sections have 2-3 sentence summaries?
- Sources mapped to each section?
- Outline approved by user?
- Agent output file saved to the correct path?
