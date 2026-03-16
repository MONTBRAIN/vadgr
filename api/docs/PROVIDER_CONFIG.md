# Provider Config

`providers.yaml` defines how Agent Forge invokes each CLI provider.

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

## Stream parser families

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
- when live logs are needed, Agent Forge rewrites that part of the command to `--output-format stream-json`

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
