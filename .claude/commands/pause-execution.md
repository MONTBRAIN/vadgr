---
description: Pause an in-progress computer use execution. Saves current state for later resumption.
---

Pause the current computer use execution.

1. Stop executing actions immediately after the current action completes
2. Take a screenshot of the current screen state
3. Record the current step number and progress
4. Report what has been completed and what remains

The execution can be resumed later with `/resume-execution`.

This is a safety mechanism. Use it when:
- You need to review what the agent has done so far
- Something looks wrong on screen
- You want to take manual control temporarily
- You need to provide additional context before continuing
