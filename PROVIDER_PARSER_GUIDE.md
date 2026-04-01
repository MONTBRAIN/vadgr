# Provider Parser Guide

`providers.yaml` defines how Vadgr invokes each CLI provider and how live logs are interpreted.

This guide explains:
- what `stream_parser` means
- what the `streaming` block does
- how to choose the right parser family by comparing real CLI output

## Minimal shape

```yaml
providers:
  my_provider:
    name: "My Provider"
    command: my-cli
    args: ["--prompt", "{{prompt}}"]
    available_check: ["my-cli", "--version"]
    timeout: 900
    stream_parser: "plain_text"
```

## Fields

| Field | Purpose |
|---|---|
| `name` | Human-readable provider name shown in the UI |
| `command` | CLI binary to execute |
| `args` | Base command arguments |
| `available_check` | Command used to detect whether the provider is installed |
| `timeout` | Provider timeout in seconds |
| `stream_parser` | Output format family used to parse live logs |
| `streaming` | Optional rewrite rules used only when live streaming is enabled |
| `models` | UI metadata for model selection |

## Placeholders

| Placeholder | Meaning |
|---|---|
| `{{prompt}}` | Replaced with the generated agent prompt |
| `{{workspace}}` | Replaced with the working directory when available |

## Parser families

`stream_parser` is a small enum, not a path to a JSON file.

Available families:

| Value | Use when the CLI emits |
|---|---|
| `plain_text` | normal line-based text output |
| `claude_stream_json` | Claude-style stream JSON events |
| `gemini_stream_json` | Gemini-style stream JSON events |
| `codex_jsonl` | Codex JSONL events |

Rule of thumb:
- pick the parser family based on the CLI stdout event shape, not the provider brand

If a new provider matches an existing family, you only need YAML changes.
If a new provider introduces a genuinely new event format, a new parser family must be added in code.

## Real sample lines

These are short representative examples from real provider output.

### `claude_stream_json`

Use this when the CLI emits assistant events with nested `message.content` blocks.

```json
{"type":"assistant","message":{"content":[{"type":"text","text":"Reading files..."}]}}
{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Grep","input":{}}]}}
{"type":"result","result":"final output"}
```

### `gemini_stream_json`

Use this when the CLI emits `message` events with `role` and plain string `content`.

```json
{"type":"init","timestamp":"2026-03-16T04:14:15.995Z","session_id":"7c08c992-51c1-4ca3-a85d-edc9d888ea26","model":"gemini-2.5-flash"}
{"type":"message","timestamp":"2026-03-16T04:14:15.996Z","role":"user","content":"Say hello in one short sentence."}
{"type":"message","timestamp":"2026-03-16T04:14:24.873Z","role":"assistant","content":"Hello! How can I help you today?","delta":true}
{"type":"result","timestamp":"2026-03-16T04:14:24.895Z","status":"success","stats":{"total_tokens":10292}}
```

### `codex_jsonl`

Use this when the CLI emits item-based JSONL events for reasoning, command execution, and agent messages.

```json
{"type":"item.completed","item":{"id":"item_0","type":"reasoning","text":"**Reviewing context**"}}
{"type":"item.started","item":{"id":"item_1","type":"command_execution","command":"cat agentic.md","aggregated_output":"","exit_code":null,"status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_14","type":"agent_message","text":"Captured categorized notes and highlights."}}
{"type":"turn.completed","usage":{"input_tokens":178570,"output_tokens":4222}}
```

### `plain_text`

Use this when the CLI just prints human-readable lines and there is no structured event format.

```text
Reading repository...
Analyzing source files...
Done
```

## Streaming rewrite

Some providers use one output mode for final JSON and another for live streaming.

Example:

```yaml
streaming:
  mode: output_format_swap
  flag: "--output-format"
  from: "json"
  to: "stream-json"
  extra_args: []
```

This means:
- base command uses `--output-format json`
- when live logs are needed, Vadgr rewrites that part of the command to `--output-format stream-json`

`streaming` controls how the command is changed.
`stream_parser` controls how the emitted lines are parsed.

## Examples

Claude:

```yaml
claude_code:
  command: claude
  args: ["-p", "{{prompt}}", "--dangerously-skip-permissions", "--output-format", "json"]
  stream_parser: "claude_stream_json"
  streaming:
    mode: output_format_swap
    flag: "--output-format"
    from: "json"
    to: "stream-json"
    extra_args: ["--verbose"]
```

Gemini:

```yaml
gemini:
  command: gemini
  args: ["--prompt", "{{prompt}}", "--approval-mode", "yolo", "--output-format", "json"]
  stream_parser: "gemini_stream_json"
  streaming:
    mode: output_format_swap
    flag: "--output-format"
    from: "json"
    to: "stream-json"
    extra_args: []
```

Codex:

```yaml
codex:
  command: codex
  args: ["exec", "{{prompt}}", "--dangerously-bypass-approvals-and-sandbox", "--json"]
  stream_parser: "codex_jsonl"
```
