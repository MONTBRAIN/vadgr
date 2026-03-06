---
description: Execute a generated workflow autonomously via computer use. Opens apps, clicks, types, and navigates the desktop.
argument-hint: [workflow-path-or-task-description]
---

Read `forge/agentic.md` to understand the full workflow context and rules.
Read `forge/Prompts/05_Computer_Use_Agent.md` for desktop execution guidance.

Execute a workflow autonomously using the Computer Use Engine.

If "$ARGUMENTS" is a path to a generated workflow (e.g., `output/my-workflow/`):
1. Read that workflow's `agentic.md` to understand its steps
2. For each step marked with execution target "computer", execute it via the Computer Use Agent
3. For steps without computer use, present them to the user for manual execution

If "$ARGUMENTS" is a task description (e.g., "Open Notepad and write a letter"):
1. Initialize the ComputerUseEngine
2. Take an initial screenshot to see the current screen
3. Break the task into sequential actions
4. Execute each action: screenshot, decide, act, verify
5. Report results when complete

Safety rules:
- Always take a screenshot before acting
- Verify each action succeeded before proceeding
- Pause before destructive actions (delete, send, purchase) and ask for confirmation
- If an action fails 3 times, stop and report the issue
