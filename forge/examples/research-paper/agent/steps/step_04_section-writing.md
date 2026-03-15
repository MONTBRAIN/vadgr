# Step 4: Section Writing

**Purpose:** Write each section of the paper with proper citations and academic rigor.

**Prompt:** `agent/Prompts/03_Academic_Writer.md`

---

## Inputs
- Approved outline: `output/{paper-name}/03_outline.md`
- Approved bibliography: `output/{paper-name}/02_bibliography.md`
- Topic brief: `output/{paper-name}/01_topic.md`

---

## Workflow

1. Review the approved outline, bibliography, and thesis statement
2. For each section in the outline, sequentially:
   a. Review the section summary and mapped sources
   b. Review the preceding section (for continuity and flow)
   c. Write the complete section with inline citations
   d. Verify every claim is backed by a source
   e. Write a transition to the next section
   f. Save the section file
3. Number each section file: `1. {Section Name}.md`, `2. {Section Name}.md`, etc.

---

## Required Outputs

### Agent Output (inter-step context)
Save to: `output/{paper-name}/sections/`
- All section files, numbered sequentially

### User Output (deliverables)
Save to: `output/{paper-name}/sections/{N}. {Section Name}.md` for each section
- Complete written sections with inline citations and transitions

---

## Quality Check

- All sections from the outline written?
- Every claim backed by a source?
- Transitions written between sections?
- Section files numbered sequentially?
