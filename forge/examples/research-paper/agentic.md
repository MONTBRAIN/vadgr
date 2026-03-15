# Research Paper, Workflow Orchestrator

## Trigger Commands

- `write a research paper`
- `start research paper`
- `/start-paper`

---

## Workflow Overview

```
Step 1         Step 2          Step 3          Step 4          Step 5
Topic     -->  Research    -->  Outline    -->  Section    -->  Review &
Selection      Phase            Generation      Writing         Assembly
               ⏸               ⏸                               ⏸
```

---

## Step 1: Topic Selection

**Step file:** `agent/steps/step_01_topic-selection.md`

Read the step file and execute it. Interview the user to establish the paper topic, target audience, scope, and desired length.

---

## Step 2: Research Phase ⏸

**Step file:** `agent/steps/step_02_research-phase.md`

Read the step file and execute it. Find and evaluate authoritative sources, compiling an annotated bibliography of 8-15 sources.

---

## Step 3: Outline Generation ⏸

**Step file:** `agent/steps/step_03_outline-generation.md`

Read the step file and execute it. Create a structured outline with a clear thesis statement and section plan, mapping sources to sections.

---

## Step 4: Section Writing

**Step file:** `agent/steps/step_04_section-writing.md`

Read the step file and execute it. Write each section of the paper sequentially with proper citations and academic rigor.

---

## Step 5: Review and Assembly ⏸

**Step file:** `agent/steps/step_05_review-and-assembly.md`

Read the step file and execute it. Compile all sections into a final paper and perform citation and structural consistency checks.

---

## After Each Step

**ALWAYS ask for user approval before saving/marking complete:**

1. Show output to the user
2. Ask: "Does this look good? Any changes needed?"
3. **Wait for user approval**
   - If changes requested → Modify and show again
   - If approved → Continue
4. Save files
5. Confirm: "Saved"

**NEVER proceed to the next step without user confirmation.**

---

## Output Structure

### Project Layout

```
research-paper/
├── README.md
├── CLAUDE.md
├── agentic.md
├── .claude/
│   └── commands/
├── agent/
│   ├── Prompts/
│   │   ├── 01_Research_Analyst.md
│   │   ├── 02_Outline_Architect.md
│   │   └── 03_Academic_Writer.md
│   ├── steps/
│   │   ├── step_01_topic-selection.md
│   │   ├── step_02_research-phase.md
│   │   ├── step_03_outline-generation.md
│   │   ├── step_04_section-writing.md
│   │   └── step_05_review-and-assembly.md
│   ├── scripts/
│   │   ├── src/
│   │   ├── tests/
│   │   ├── requirements.txt
│   │   └── README.md
│   └── utils/
│       ├── code/
│       └── docs/
└── output/
```

### Paper Output

```
output/{paper-name}/
├── 01_topic.md
├── 02_bibliography.md
├── 03_outline.md
├── sections/
│   ├── 1. {Section Name}.md
│   ├── 2. {Section Name}.md
│   └── ...
└── final_paper.md
```

---

## Quality Checks

| Step | Check |
|------|-------|
| 01 | Topic, audience, scope, and length defined? User confirmed? |
| 02 | 8-15 sources found? Each annotated? Relevance scores assigned? User approved? |
| 03 | Thesis statement clear? All sections summarized? Sources mapped? User approved? |
| 04 | Every section written? Every claim cited? Transitions present? |
| 05 | All citations consistent? No orphaned sources? Final paper assembled? User approved? |
