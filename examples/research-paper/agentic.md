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

**Purpose:** Establish the paper topic, target audience, scope, and desired length.

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

**Save:** `output/{paper-name}/01_topic.md`

---

## Step 2: Research Phase ⏸

**Purpose:** Find and evaluate authoritative sources for the paper.

**Read:** `Prompts/1. Research Analyst.md`

**Workflow:**

1. Review the topic brief from Step 1
2. Search the web for authoritative and academic sources on the topic
3. Evaluate each source for relevance, recency, and authority
4. Compile an annotated bibliography with 8-15 sources
5. For each source include: title, author, year, URL, 2-sentence annotation, relevance score (1-5)
6. Present the annotated bibliography to the user for review

**Wait for user approval. If changes requested, search for additional sources or remove weak ones.**

**Save:** `output/{paper-name}/02_bibliography.md`

---

## Step 3: Outline Generation ⏸

**Purpose:** Create a structured outline with a clear thesis and section plan.

**Read:** `Prompts/2. Outline Architect.md`

**Workflow:**

1. Review the topic brief and approved bibliography
2. Identify major themes and arguments from the sources
3. Draft a thesis statement
4. Structure the paper into sections (Introduction, Body sections, Conclusion)
5. Write a 2-3 sentence summary for each section
6. Map specific sources to each section
7. Present the complete outline to the user for review

**Wait for user approval. If changes requested, revise structure or thesis.**

**Save:** `output/{paper-name}/03_outline.md`

---

## Step 4: Section Writing

**Purpose:** Write each section of the paper with proper citations and academic rigor.

**Read:** `Prompts/3. Academic Writer.md`

**Workflow:**

1. Review the approved outline, bibliography, and thesis statement
2. For each section in the outline, sequentially:
   a. Review the section summary and mapped sources
   b. Review the preceding section (for continuity and flow)
   c. Write the complete section with inline citations
   d. Verify every claim is backed by a source
   e. Write a transition to the next section
   f. Save the section file
3. Number each section file: `1. {Section Name}.md`, `2. {Section Name}.md`, etc.

**Save:** `output/{paper-name}/sections/{N}. {Section Name}.md` for each section

---

## Step 5: Review and Assembly ⏸

**Purpose:** Compile all sections into a final paper and perform quality review.

**Workflow:**

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

**Save:** `output/{paper-name}/final_paper.md`

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
