# Step 1: Gather Requirements

**Purpose:** Understand what the user wants to automate and what good output looks like.

**Prompt:** None (orchestrator handles this directly)

---

## Inputs

- User's description of the workflow they want to build
- Optional: quality samples showing what good output looks like

---

## Workflow

1. **Ask for the description first. Wait for the response before continuing.**

   ```
   Describe the workflow you want to build. What should it accomplish?
   ```

2. **After receiving the description:**

   Analyze the description. Try to infer: the major phases of work, what inputs the workflow takes, what outputs it produces, whether desktop interaction is needed, and who will use it. If the description gives you enough to infer all of this, proceed directly to compiling the requirements summary without asking further questions.

   If the description is ambiguous about the process (you cannot tell what the major steps are or how the work flows), ask one follow-up:

   ```
   Can you describe the main steps or phases of the work? What does someone
   currently do manually that this workflow should handle?
   ```

   Only ask this if you genuinely cannot infer the process from the description. Do not ask it as a formality.

3. **Optionally accept quality samples:**

   If the user wants to provide examples of what good output looks like, accept them. Each sample may include an optional short label describing what it shows. Quality samples are not required. If the user does not offer them, do not ask.

4. **Conventions (not questions):**

   - Output location is always `output/{kebab-case-name}/`. Do not ask.
   - Computer use is a flag. If the description mentions desktop interaction (opening apps, clicking buttons, filling forms, navigating GUIs, automating tasks that require seeing the screen), set computer_use to true. Otherwise default to false. Do not ask.
   - Approval gates, user type, and output structure are determined in Step 2. Do not ask.

5. **Compile a requirements summary containing:**

   1. **Name.** A kebab-case name inferred from the description.
   2. **Purpose.** 2-3 sentences describing what the workflow accomplishes.
   3. **Steps (inferred).** The major phases of work as you understand them. Mark as "inferred" if not stated explicitly.
   4. **Inputs.** What the user provides to start the workflow.
   5. **Outputs.** Files, folders, or artifacts the workflow produces.
   6. **Computer use.** true or false, with the reason.
   7. **Quality samples.** Any provided examples (or "none").
   8. **Output location.** `output/{name}/`

6. Present the summary to the user for confirmation.

---

## Required Outputs

### Agent Output (inter-step context)

Held in context for subsequent steps. No file saved.
- Requirements summary with: name, purpose, inferred steps, inputs, outputs, computer_use flag, quality samples, output location

### User Output (deliverables)

None. This step produces inter-step context only.

---

## Quality Check

- Description provided and understood?
- Steps inferred or clarified?
- Requirements summary confirmed by user?
