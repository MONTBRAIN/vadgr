# Step 5: Review and Assembly

**Purpose:** Compile all sections into a final paper and perform quality review.

**Prompt:** None (mechanical compilation and review step)

---

## Inputs
- All section files: `output/{paper-name}/sections/`
- Approved outline: `output/{paper-name}/03_outline.md`
- Approved bibliography: `output/{paper-name}/02_bibliography.md`
- Topic brief: `output/{paper-name}/01_topic.md`

---

## Workflow

1. Read all section files from `output/{paper-name}/sections/` in order
2. Compile them into a single document
3. Check citation consistency:
   - Every inline citation matches a bibliography entry
   - No bibliography entries are unused
   - Citation format is consistent throughout
4. Check structural consistency:
   - Transitions between sections are smooth
   - Thesis is supported across all sections
   - Introduction previews what follows; conclusion summarizes what was covered
5. Generate the final paper with title, abstract, all sections, and bibliography
6. Present a summary to the user:

```
Paper: {title}
Thesis: {thesis statement}
Sections: {count}
Sources cited: {count}
Approximate length: {word count estimate}
```

**Wait for user approval. If changes requested, revise and recompile.**

---

## Required Outputs

### Agent Output (inter-step context)
Save to: `output/{paper-name}/final_paper.md`
- Complete compiled paper

### User Output (deliverables)
Save to: `output/{paper-name}/final_paper.md`
- Final paper with title, abstract, all sections, and bibliography

---

## Quality Check

- Every inline citation matches a bibliography entry?
- No unused bibliography entries?
- Introduction, body sections, and conclusion all present?
- Paper approved by user?
- Agent output file saved to the correct path?
