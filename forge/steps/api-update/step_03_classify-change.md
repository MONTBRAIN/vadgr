# Step 3: Classify the Change

**Purpose:** Decide whether to patch existing files or fully regenerate the agent.

**Prompt:** None (orchestrator handles this directly)

---

## Inputs

- Change set from Step 1
- Existing workflow state from Step 2

---

## Workflow

1. Use the change set and existing state to decide: **patch** or **regenerate**.

### Patch (targeted edits to existing files)

Apply a patch when the change is additive or refinable within the current structure:

- Only `description` changed, and the new description implies the same number of steps
  and the same areas of expertise as the original.
- Only `samples` changed (new or updated calibration examples).
- `computer_use` changed from false to true, and the existing structure is otherwise
  valid (orchestrator and at least one prompt exist).
- `computer_use` changed from true to false.
- A combination of the above.

A description change is safe to patch when:
- The original and updated descriptions both imply the same complexity level
  (`simple` or `multi_step`).
- The core task is the same but the wording, scope, or domain has shifted moderately.
- No new phases of work appear that would require a new step or a new agent.

### Full Regeneration

Regenerate the entire agent folder (using the same approach as `api-generate.md`) when:

- The updated description implies a different complexity level than the original.
- The updated description introduces fundamentally different phases of work that
  require new agents not present in the current roster.
- The existing files are structurally broken: `agentic.md` is missing required sections,
  fewer than the expected number of prompt files exist, or cross-references are broken.

**When in doubt, patch.** A patch that is slightly too conservative is safer than a
regeneration that discards existing customizations.

2. **Save in context:**
   ```
   update_mode: patch | regenerate
   change_set: [list of changed field names]
   affected_files: [list of files that need changes]
   ```

---

## Required Outputs

### Agent Output (inter-step context)

Held in context for subsequent steps. No file saved.
- `update_mode`: patch or regenerate
- `change_set`: list of changed fields
- `affected_files`: list of files to modify

### User Output (deliverables)

None. This step produces inter-step context only.

---

## Quality Check

- Classification justified by change magnitude?
- Patch preferred when in doubt?
- Affected files list complete?
