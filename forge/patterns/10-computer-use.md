# Pattern 10: Computer Use

## What

A workflow pattern that gives agents eyes (screenshots) and hands (mouse, keyboard) to execute tasks autonomously on the desktop. The Computer Use Engine is provided by the [`vadgr-computer-use`](https://github.com/MONTBRAIN/vadgr-computer-use) package (`pip install vadgr-computer-use`). A specialized Computer Use Agent decides what to see and do.

This pattern transforms workflows from "instructions a human follows" into "instructions the computer follows on its own."

## When to Use

- The workflow needs to open applications, click buttons, fill forms, or navigate GUIs
- Steps involve interacting with software that has no API or CLI (only a visual interface)
- The workflow should execute autonomously without human keyboard/mouse input
- UI testing, form automation, data entry, or desktop task orchestration

## When NOT to Use

- The task can be done entirely via CLI commands, APIs, or file manipulation
- The workflow only generates files (use standard generate mode)
- The target application has a well-documented API that is more reliable than visual interaction

## Structure

### Two Modes

**Library mode (agent-driven).** An LLM agent calls the engine as a tool. The agent sees the screenshot, decides what to do, and tells the engine to act. The agent is the brain; the engine is just eyes and hands.

```python
engine = ComputerUseEngine()
screen = engine.screenshot()        # agent sees the screen
engine.click(500, 300)              # agent tells engine to click
engine.type_text("hello")           # agent tells engine to type
```

**Autonomous mode (engine-driven).** The engine runs its own loop, calling an LLM API directly. Useful when no external agent is hosting the workflow. The provider is configured in the generated project's `computer_use/config.yaml` (scaffolded by forge) and is not tied to any specific LLM.

```python
engine = ComputerUseEngine()  # provider loaded from config.yaml
results = engine.run_task("Open Notepad and type hello")
```

### Workflow Step Format

When a step targets computer use instead of a human, its instructions change:

```
HUMAN-TARGETED (standard):
  "Create a file REQUIREMENTS.md with the project requirements"

COMPUTER-USE-TARGETED:
  "Open the system text editor.
   Create a new file.
   Type the following requirements: [content]
   Save as REQUIREMENTS.md in the project folder.
   VERIFY: File REQUIREMENTS.md exists in the project folder."
```

Computer-use-targeted steps are visual and sequential. Each instruction describes what to see and do on screen, followed by a verification condition.

### Integration in a Workflow

```
agentic.md step:

## Step 4: Fill Application Form

**Read:** agent/Prompts/05_Computer_Use_Agent.md

**Execution Target:** computer

1. Open the web browser
2. Navigate to the application URL
3. Fill in each form field from the gathered data
4. Click Submit
5. VERIFY: Confirmation page is visible

**Save:** Screenshot of confirmation page to output/{task}/confirmation.png
```

## Key Conventions

1. **Computer use is optional.** Only include it when the workflow genuinely needs desktop interaction. Generate mode must work without it.
2. **Platform detection is automatic.** The engine detects WSL2, Linux, Windows, or macOS at startup and loads the correct backend.
3. **Vision-only by default.** No browser automation libraries, no DOM inspection. Only screenshots and OS accessibility APIs.
4. **Verify every action.** After each action, take a new screenshot and confirm the expected change happened.
5. **Fail gracefully.** If an element is not found or an action fails, retry or escalate, never crash silently.

## Available Actions

| Action | Method | Description |
|--------|--------|-------------|
| Screenshot | `engine.screenshot()` | Capture full screen as PNG |
| Click | `engine.click(x, y)` | Left click at coordinates |
| Double click | `engine.double_click(x, y)` | Double click |
| Right click | `engine.right_click(x, y)` | Right click |
| Type | `engine.type_text("...")` | Type text into focused field |
| Key press | `engine.key_press("ctrl", "s")` | Press key combination |
| Scroll | `engine.scroll(x, y, amount)` | Scroll at position |
| Drag | `engine.drag(x1, y1, x2, y2)` | Drag from A to B |
| Find element | `engine.find_element("Save")` | Locate UI element by description |
| Screen size | `engine.get_screen_size()` | Get display dimensions |

## Example

A workflow that automates filling a web form:

```
Step 1: Gather Data (direct, no computer use)
  Collect the user's name, email, and message from input

Step 2: Open Browser (computer use)
  Open Chrome. Navigate to https://example.com/contact.
  VERIFY: Contact form is visible on screen.

Step 3: Fill Form (computer use)
  Click the Name field. Type the user's name.
  Click the Email field. Type the user's email.
  Click the Message field. Type the message.
  VERIFY: All three fields are filled.

Step 4: Submit (computer use)
  Click the Submit button.
  VERIFY: Success message or confirmation page appears.

Step 5: Report (direct, no computer use)
  Save a screenshot of the result. Report success or failure.
```

Steps 2-4 use the Computer Use Agent. Steps 1 and 5 are handled directly by the orchestrator.
