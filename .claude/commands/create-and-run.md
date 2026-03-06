---
description: Generate a workflow AND immediately execute it via computer use. Full pipeline from description to done.
argument-hint: [task-description]
---

Read `forge/agentic.md` fully. This is your workflow guide for the entire lifecycle.

This is "full mode": generate a workflow and then execute it.

**Phase 1: Generate**
Run the standard workflow creation pipeline (Steps 1-7 from agentic.md) using "$ARGUMENTS" as the task description. Follow all approval gates.

**Phase 2: Execute**
Once the workflow is generated and approved:
1. Read `forge/Prompts/05_Computer_Use_Agent.md`
2. Initialize the ComputerUseEngine
3. Execute each computer-use step in the generated workflow
4. Present results

This command combines `/create-workflow` and `/execute-workflow` into one flow.
The user must approve the generated workflow before execution begins.
