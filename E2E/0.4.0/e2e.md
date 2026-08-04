# Native loop 0.4.0 - end to end test runbook

Validation of the **native agent loop** and its **control-plane tools** (PR #169).
The loop owns the conversation, the tool-use cycle, image pruning and the resume
journal; the control-plane server gives the model eight in-process tools for
progress, status and human-in-the-loop. Unit tests prove each piece in isolation;
they do not prove that a real model, given a goal, finds the right tool, calls it
with arguments it invented, and that the journal that comes out can actually
resume a crashed run.

> **Status: run on WSL, 2026-07-30. 107 of 110 cells executed, 6 findings,
> 3 of them fixed on this branch and re-run green.** Automated gate
> **engine 110** (was 101; +9 regression tests, each verified to fail without its
> fix), api 516. Every axis below is **enumerated, not sampled**: each part states
> its axes, their product, and the state of every cell. Three cells are open and
> each says why. **F3, F5 and F6 are fixed**; F1, F2 and F4 are recorded and
> deferred with their reason. Nothing is marked pass that was not executed and
> read back from the journal.

### Coverage

| Part | Axes | Cells | Run | Open |
|---|---|---|---|---|
| L loop contract | 6 properties + pruning (4 x 3) | 18 | 18 | 0 |
| C control-plane tools | 8 tools x every branch of their contract | 14 | 12 | 2 |
| R crash + resume | prior work 2 x end-state 2 x side effect 2 | 8 | 7 | 1 |
| P policy | mode 4 x risk 3 x denylist 2, + redaction 8, + ungated 1 | 33 | 33 | 0 |
| N channels | channel 2 x importance 3, + routing 3, + OS 4 | 13 | 13 | 0 |
| A auth | strategy x token state 14, + store x OS 4 | 18 | 18 | 0 |
| M MCP host | 6 host contracts | 6 | 6 | 0 |
| | | **110** | **107** | **3** |

Collapsed deliberately, with the reason: `notify_user` x *message content* is not
an axis (the string is opaque to the router); tool x *argument values* is not an
axis for model-driven items - the rule from the engineering standard is to enumerate
**outcomes**, not inputs, because the model chooses the inputs.

## SCOPE EXCEPTION FOR THIS MINOR - read this first

the engineering standard says a real e2e drives the product's own surface, and that a
harness which imports the module under test is an **acceptance test**, not an
e2e. **`0.4.0` cannot meet that bar**, and the exception is deliberate and
bounded:

- The engine ships as a **library that nothing calls**. `POST /api/agents/{id}/run`
  goes through `ExecutionService` to the old `CLIAgentProvider`; nothing in `api/`
  or `cli/` imports `engine/`. The PR states this under *Not in this slice*.
- So this runbook drives the loop **directly** (`AnthropicOAuthProvider.run_agent`)
  or through the CLI where a path exists. That is an **acceptance test**, and every
  result below must be read as one.

**The exception expires at `0.4.1`.** That patch puts the engine on the production
path, and from that minor on the runbook drives **both real surfaces**:

- **the API + the run WebSocket**, the way the phone does - the only way to know a
  mobile call behaves, since the request/response shapes and the WS event stream
  are what the mobile client codegens against;
- **the CLI** (`vadgr run`, `vadgr stream`) - the on-box owner path, with its
  own users and its own failure modes.

**Neither substitutes for the other.** A green CLI run says the loop works and
nothing about whether the JSON the phone parses is right; a green API run says the
wire is right and nothing about the on-box path. `E2E/0.4.1/e2e.md` supersedes this
file and covers both. Do not carry this exception forward: it exists because there
is no surface to drive, not because importing is acceptable.

## The approach

Everything else in §1a still applies, and these are the rules that make the
results mean anything:

- **A real model drives it.** The loop *is* the agent here: give it a goal-level
  task and let it choose its own tools. Never call a tool directly to "test" it -
  that proves the function works, not that the tool is findable.
- **Goal-level tasks, never op-level.** "Plan this work and check with me before
  anything irreversible" - not "call `todo_write` then `request_approval`". A task
  that names the tool has not tested discovery.
- **The verdict comes from `trajectory.jsonl`, not the model's prose.** The journal
  is written by the loop, not by the model, so it can contradict it. **A
  self-reported success with no confirming journal line is a FAIL.**
- One run at a time. Record the `run_id` of each so a finding is reproducible.

## When a test surfaces a bug

Finding one is the point. Root-cause it in the source citing `file:line` - a flaky
environment is not a root cause until the code says so - fix it on the PR branch
with a test that fails without the fix, re-run the part live, and record the patch
in the patch log with this runbook in the *found by* column.

## Prerequisites

- Anthropic credentials reachable: a Claude Code OAuth token, or `ANTHROPIC_API_KEY`.
- A scratch runs dir, so a test run never lands in `~/.vadgr/runs/`:
  `export RUNS=$(mktemp -d)`.
- Nothing else. The loop needs no daemon, no tailnet and no phone at `0.4.0`.

## Automated gate (necessary, not sufficient)

Green on the branch before any live part:

- `PYTHONPATH=. python3 -m pytest engine/tests/ -q` -> **110 passed** (http, auth
  incl. per-OS token resolution, format, provider invariants, the eight
  control-plane tools, policy, channels, trajectory, pruning, ports - plus the 9
  regression tests this runbook's findings added, each verified to fail with its
  fix reverted).
- `python3 -m pytest api/tests/ -q` -> **516 passed**, no regressions.

## Part L: the loop's own contract

Seven properties; the pruning property is itself a 4x3 matrix.

| # | Property | Expected | Status |
|---|---|---|---|
| L1 | Termination | no-tool task returns at `total_iterations == 1` | **pass** |
| L2 | Journal ordering | `response -> in_flight(n) -> done(n)`, in_flight **before** dispatch | **pass** |
| L3 | Tool error is fed back | `error` line on that `seq`, loop continues, model reads it | **pass** |
| L4 | Multi-tool iteration | monotonic `seq`; `total_iterations` counts model calls, not tool calls | **pass** |
| L5 | Usage accounting | per-response usage reconciles with the totals | **pass** |
| L6 | Budget exhaustion | `MaxIterationsExceeded` raised - not a park, not a hang | **pass** |
| L7 | Image pruning | last `keep_last` images survive; the rest become the placeholder | **pass 12/12** |

**Measured:**

- L1 `L1-terminate`: `total_iterations=1`, journal `{response: 1}`, no tool line,
  final text `DONE`. The loop stops when the model stops asking for tools.
- L3 `L3-toolerror`: the model sent `status: "completed"`; the tool's vocabulary is
  `pending|in_progress|done|cancelled`, so it raised. Journal:
  `{response: 2, in_flight: 1, error: 1}` - the `in_flight` at `seq 0` is closed by
  an **`error`**, not a `done`, the loop continued, and the model quoted the message
  back verbatim. **A tool error is data, not a crash.** (The off-vocabulary guess
  itself is **F3**.)
- L4 `partC`: 3 tool calls across 4 iterations, `seq` 0,1,2 with no gap.
- L6 `L6-budget`: budget 1, task needs three turns -> `MaxIterationsExceeded: Agent
  did not finish in 1 iterations`. The completed first call is journaled
  `in_flight`+`done` before the raise, so the journal is resumable.
- L5 `v-todo`: per-response `usage` lines `1303+1493+1623 = 4419` input and
  `134+95+163 = 392` output, **exactly** the reported totals. The loop's own
  accounting line was never redacted; the *copy inside the recorded response* was,
  which is **F6** - fixed, and both now agree line by line.
- L7 `prune_old_images`: `images {0,1,3,5}` x `keep_last {0,1,3}` = 12 cells, all
  correct - `intact == min(images, keep_last)`, `pruned == max(0, images-keep_last)`,
  including the boundary `keep_last=0` and images nested inside `tool_result`.

## Part C: every control-plane tool x every outcome

Axes: **8 tools**, and for the human-facing ones **every branch of their contract**
(approve / reject / timeout / denylisted, options / no options, override channel).
Model-driven, so the rule is *enumerate the outcomes*, not the arguments.

| # | Tool | Outcome under test | Status |
|---|---|---|---|
| C1 | `todo_write` | model writes a plan unprompted by tool name | **pass** |
| C2 | `todo_update` | status transition on a real id | **pass** |
| C2b | `todo_update` | a synonym status (`completed`) is accepted, not an error | **pass** (F3 fix) |
| C3 | `report_progress` | `progress` event + journal line | **pass** |
| C4 | `get_run_status` | model **quotes the result back accurately** | **pass** |
| C5 | `request_approval` | **approve** -> loop resumes and acts | not run* |
| C6 | `request_approval` | **reject** -> normal tool result, loop continues | **pass** |
| C7 | `request_approval` | **timeout** -> normal tool result, fail-closed | **pass** |
| C8 | `request_approval` | **denylisted** -> `auto_deny` before the human | **pass** (Part P, 12 cells) |
| C9 | `ask_user` | free answer steers what happens next | **pass** |
| C10 | `ask_user` | **negative**: unambiguous task must NOT ask | **pass** |
| C11 | `ask_user` | with `options` -> answer constrained to them | not run |
| C12 | `propose_plan` | proposed **before** execution, and blocks | **pass** |
| C13 | `notify_user` | routed to the active channel with `importance` | **pass** |
| C14 | `notify_user` | per-call `channel` override reaches the other channel | **pass** (Part N) |

\* C5's task produced `ask_user` instead - the model judged it needed information
first. The tool worked; the *approve* branch of `request_approval` is still owed.

**Measured:**

- C2 `C2-todo`: `todo_write -> {"ok": true, "todos": [...]}`, then
  `todo_update -> {"ok": true, "todo": {"id": "1", ..., "status": "done"}}`. An
  unknown id raises `unknown todo id: <id>` (`engine/tools/todo.py:79`) - the id is
  validated, not silently accepted.
- C6 `{"decision": "reject", "note": "reject"}`, 1 `await_user` line, loop
  continued, model replied `REJECTED` and stopped. **A rejection is not a crash.**
- C7 timed out -> `{"decision": "reject"}`. **Timeout is fail-closed**, arrives as
  an ordinary tool result, loop continued, no exception.
- C9 `{"answer": "approve", "timed_out": false}`, 1 `await_user` line.
- C10 `C10-noask`: "add 17 and 25" -> `total_iterations=1`, journal `{response: 1}`,
  **no tool call at all**, final text `42`. The tools do not make it chatty.
- C12 `C12-plan`: `propose_plan -> {"decision": "approve", "feedback": "ok"}` with
  an `await_user` line in the journal - the plan **blocks** for the human, and it is
  the model's first action, before any execution.
- C13 `C13-notify`: `{"ok": true, "delivered": ["cli"]}`, CLI line
  `[info] Nightly backup completed successfully.` - the model picked `low` for a
  routine event, and `low` renders as `[info]`.

## Part R: crash and resume - the state matrix

Axes: **prior completed work (2) x journal end-state (2) x countable side effect
(2) = 8 cells.** The failure to hunt is **silent replay**: a replayed run also ends
`completed`, so "it finished after a restart" proves nothing. Every cell here uses
`notify_user` as the countable effect - each call appends one line to a file, so a
replay is visible as a duplicated line.

| # | prior work | ends | side effect | Expected | Status |
|---|---|---|---|---|---|
| R1 | none | clean | n/a | no dangling; `find_latest` does **not** offer it | **pass** |
| R2 | none | **dangling** | no | journal ends on an unmatched `in_flight` | **pass** |
| R3 | none | dangling | no | `find_latest()` identifies it by the dangling record | **pass** |
| R4 | none | dangling | no | `resume()`: `next_seq` == dangling `seq` | **pass** |
| R5 | **yes (2 calls)** | dangling | **yes, counted** | completed work **NOT** re-executed | **pass** |
| R6 | yes | dangling | yes | dangling call revalidated via `idem`, not re-issued | **not testable at 0.4.0 - F4** |
| R7 | yes | clean | yes | resume of a finished run offers nothing to redo | **pass** |
| R8 | yes | clean | yes | side effect happened **exactly once** per call | **pass** |

**Measured - R5, the load-bearing cell.** Run `r5`: the model was asked to notify
three times; the process was `SIGKILL`ed **after `in_flight` was journaled for the
third call and before it dispatched**.

```
side-effect file : 2 lines   ["[notify] one", "[notify] two"]
journal          : seq 0 in_flight+done, seq 1 in_flight+done, seq 2 in_flight (open)
find_latest      : "r5"
completed_seqs   : [0, 1]
next_seq         : 2        (== the dangling seq, not 3)
dangling         : control__notify_user {"message": "three"}
dangling idem    : sha256:6671b08e...babd6ce
```

A replay would have re-notified `one` and `two` and left **4** lines. The file has
**2**. `resume()` positions at `seq 2` - the first *uncompleted* step - so the two
finished calls are skipped, not repeated.

**R7/R8** ran the same task to completion: 3 lines, `completed_seqs=[0,1,2]`,
`dangling=None`, `next_seq=3`, and `find_latest()` returns **`None`** - a finished
run is never offered for resume, and each call fired exactly once.

## Part P: policy - the full decision matrix (24/24 cells, RUN)

Axes: **auth mode (4) x declared risk (3) x denylist hit (2) = 24 cells.** The
policy hook is a pure function, so every cell is cheap and none is sampled.

| mode | risk | denylisted | outcome | run |
|---|---|---|---|---|
| bypass | low / medium / high | no | `auto_allow` | pass |
| bypass | low / medium / high | **yes** | `auto_deny` | pass |
| default | low | no | `auto_allow` | pass |
| default | medium | no | `auto_allow` | pass |
| default | **high** | no | **`needs_human`** | pass |
| default | low / medium / high | **yes** | `auto_deny` | pass |
| autonomous | low | no | `auto_allow` | pass |
| autonomous | medium | no | `auto_allow` | pass |
| autonomous | **high** | no | **`needs_human`** | pass |
| autonomous | low / medium / high | **yes** | `auto_deny` | pass |
| paranoid | low / medium / high | no | **`needs_human`** | pass |
| paranoid | low / medium / high | **yes** | `auto_deny` | pass |

**P1 Denylist precedence** - confirmed in all 12 denylisted cells: a denylist hit
is `auto_deny` in **every** mode, `bypass` included.
**P2 `bypass`** auto-allows all three risks. **P3 `paranoid`** consults a human at
all three risks - confirmed live end to end (a low-risk scratch write was gated,
rejected, and the loop continued).

**P4 Redaction - pass, live and enumerated.** Run `p4b`: the model called
`report_progress` with a payload matching the credential pattern; the journal holds
`{"message": "build [REDACTED] finished"}` and **zero** raw occurrences of the
value. The key/value matrix (8 cells) behaves as specified: secret-named keys are
redacted regardless of value (including `password: null`), `sk-`/`Bearer` values are
redacted regardless of key, nesting through lists and dicts is covered, and a
too-short `sk-` or an English sentence containing the word "secret" is **not**
redacted - the pattern is not a keyword filter. Over-matching is **F6**.

*A note the next runbook should inherit:* the first attempt (`p4`) failed to reach
the tool at all - the model **refused to echo what looked like a real API key** and
wrote an explanation instead. When a model-driven test needs a specific payload,
the payload must not look like a live secret, or the model becomes the blocker.

**P5 Ungated dispatch - pass.** Run `p5` with `policy.check()` counted and the mode
set to `paranoid` (which asks on *every* gated call): 2 tools dispatched,
**`policy.check` called 0 times**, 0 `await_user` lines. Confirms the gate is
reached only through `request_approval` (`engine/tools/hitl.py:64`) and that
ordinary tool dispatch is not policed. See **F2**.

## Part N: channels - where a human is actually reached

Axes: **channel (2) x importance (3) = 6**, plus **routing (3)**, plus **desktop
command selection x OS (4)**. The desktop channel takes an injectable runner, so
its per-OS command *selection* is assertable from any host; whether the native
command works is per-OS and owed (see the OS table).

| channel | low | normal | high |
|---|---|---|---|
| cli | `[info] <msg>` | `[notify] <msg>` | `[!]  <msg>` |
| desktop (Linux) | `notify-send` | `notify-send` | **`zenity`** (modal) |

All 6 pass. `high` escalates in both channels - a toast on `low`/`normal`, a modal
on `high`.

**Routing (3 cells):** no override -> the active channel (`["cli"]`, 0 desktop
commands); `channel="desktop"` -> `["desktop"]`, the CLI untouched; an unknown
channel -> `ValueError: unknown channel: nope` rather than a silent drop.

**Command selection x OS (4 cells, injected runner):**

| OS | notify | request |
|---|---|---|
| Linux | `notify-send` | `zenity` |
| macOS | `osascript` | `osascript` |
| Windows | `powershell` | `powershell` |
| WSL | `notify-send` | `zenity` (Linux-side desktop, intended) |

## Part A: auth - strategy x token state

Axes: **3 strategies x their token states = 16 cells**, plus **store resolution x
OS = 4**. All 20 run.

| strategy | state | Outcome | Status |
|---|---|---|---|
| oauth | valid | injects the cached token, **0 refresh calls** | **pass** |
| oauth | inside the refresh window | refreshes *pre-emptively*, injects the new token | **pass** |
| oauth | expired | refreshes, injects the new token | **pass** |
| oauth | expired, no `refreshToken` | `CredentialsError: No refresh token available` | **pass** |
| oauth | no credentials file | `CredentialsMissingError` naming `claude setup-token` | **pass** |
| oauth | empty credentials block | same error - an empty block is not a valid token | **pass** |
| oauth | refresh endpoint returns 400 | `CredentialsError: Token refresh failed (HTTP 400)` | **pass** |
| oauth | **401 -> refresh succeeds** | token dropped, refreshed once, **retry signalled** | **pass** |
| oauth | 401 -> refresh fails | returns `False` - terminal, no retry storm | **pass** |
| api_key | env var set | injected as `x-api-key` | **pass** |
| api_key | env var unset | `RuntimeError` naming the variable | **pass** |
| api_key | 401 | `False` - terminal, a bad key is not refreshable | **pass** |
| none | any | injects nothing | **pass** |
| none | 401 | `False` - terminal, a local 401 is misconfiguration | **pass** |

**A1 (live):** every run in this document authenticated through the OAuth path
against the real API - the strategy is exercised end to end on every part above.

**A3 store resolution x OS (4 cells):** macOS -> `KeychainTokenStore`; Linux,
Windows and WSL -> `FileTokenStore`. WSL resolves the **Linux-side** home, as
intended. Selection is proven from this host; the Keychain and Windows stores are
**owed on their own OS** and are the only genuinely per-OS thing in `0.4.0`.

**A4 wire-format invariants:** `user_agent = "claude-cli/2.1.2 (external, cli)"`,
`anthropic-beta: oauth-2025-04-20,interleaved-thinking-2025-05-14`, and the Claude
Code system prefix - all asserted by the automated gate, and any 400 from the real
API in the live runs above would have broken every part. None did.

## Part M: the MCP host

Six contracts. Stub servers are correct here: the object under test is the host's
aggregation and routing, not a model behaviour.

| # | Contract | Expected | Status |
|---|---|---|---|
| M1 | Aggregation | every server's tools in one list | **pass** |
| M2 | Namespacing | `<server>__<tool>`; a name in two servers does **not** shadow | **pass** |
| M3 | A server that fails to start | run continues, its tools simply absent | **pass** (F5 fix) |
| M4 | Duplicate server names | startup error, never a silent shadow | **pass** |
| M5 | A tool that raises | propagates to the loop, which journals `error` (see L3) | **pass** |
| M6 | `aclose` | every server released | **pass** |

**Measured live (`v-mcp`), after the F5 fix:** a run configured with a healthy
external server (`notes`) and a broken one (`calendar`, refusing connections)
**completed**. The host logged
`MCP server 'calendar' failed to start and was dropped`, the model discovered and
called `notes__save_note`, and the run finished. Before the fix this same
configuration raised out of `connect()` and no run started at all.

**Measured (host contracts):** two servers each exposing `ask_user` aggregate to
`control__ask_user` and `cua__ask_user`, and each routes to its own server. An
un-namespaced name (`ask_user`) and an unknown server both raise
`UnknownToolError` - no fallback guessing. Two servers named `cua` raise
`MCP server name collision` at connect. `aclose()` closed both.

## Findings

### F1: `default` and `autonomous` are indistinguishable

The enumeration shows **identical outcomes in all 24 cells**. Two of the four
advertised modes are the same mode. Not a defect in `0.4.0` - autonomy v2 (risk
classes, decision tables, ordered overrides) is `vadgr 0.6.0` - but it must not be
described as a working four-mode system before then.

### F2: the gate is advisory twice over

**Only 5 of 24 cells consult a human**, and reaching one requires *both*:

1. the model **chooses** to call `request_approval` - dispatch itself is ungated
   (**proven live in P5**: 0 `policy.check` calls across 2 dispatched tools in
   `paranoid` mode), `policy.check()` is called from exactly one place
   (`engine/tools/hitl.py:64`), and there is no allowlist; **and**
2. the model **self-declares** `risk: "high"` - the risk is the model's own
   assessment, not a classification of the call.

Observed live: asked to email an external address with sign-off, the model called
`request_approval` with **`risk: "low"`**, so `default` mode auto-allowed it and the
human was never asked. Sending mail off the machine is `external` - the
highest-consequence class in the target design - and the model rated it low.

### F3 (fixed): the todo status vocabulary was not the model's vocabulary

`VALID_STATUSES = (pending, in_progress, done, cancelled)`
(`engine/tools/todo.py:11`). Given a plain goal, the model reached for
**`completed`** and got `ValueError: invalid todo status: completed`. The status is
declared as a JSON-Schema `enum`, but the enum is **advisory** - the invalid value
reached the tool and came back as an error string, costing an iteration. The loop
recovered correctly (that is L3), so this was ergonomics, not correctness.

**Fixed** (`engine/tools/todo.py`): the common synonyms map to the canonical
status (`completed`/`complete`/`finished`/`success` -> `done`, `in-progress` and
`in progress` -> `in_progress`, `canceled` -> `cancelled`, `todo` -> `pending`),
and both errors now name what is legal - the status error lists all four values,
the id error lists the known ids. Re-run live (`v-todo`): the same kind of task
now produces **2 tool calls, 2 `done` lines and zero `error` lines**, where before
it burned an iteration.

### F4 (deferred, with reason): `idem` is written but read by nothing

Every `in_flight` record carries `idem: sha256:...` (`engine/trajectory.py:111`)
and `PolicyDecision` declares an `idem` field, but **no non-test code reads
either**. `resume()`'s docstring promises a dangling action is "re-validated live
via its `idem` before any re-do" - there is no re-do path at all, so the promise is
untestable rather than broken. R6 is therefore **owed at the minor that wires
resume into `run_loop`**, not owed here. The docstring should say what is built.

### F5 (defect, fixed): one broken MCP server took down the whole run

`MCPHost.connect()` (`engine/mcp.py:52-69`) iterates the servers and awaits
`list_tools()` inline with no per-server guard. A server that fails to start raises
straight out of `connect()`, so **the run never begins** and the healthy servers'
tools are lost with it. Measured: a host of `[control, broken]` raised
`RuntimeError: broken: cannot start`; `control__ask_user` never became available.

That is exactly backwards for a daemon whose value is the tools that *do* work, and
it was a live risk the moment a third-party MCP server was configured.

**Fixed** (`engine/mcp.py`): each server's `list_tools()` is guarded; a server that
fails to start is dropped with a warning and recorded in **`MCPHost.failed()`**, so
a degraded host is *visible* rather than silent, and every healthy server stays
available. A **name collision still raises** - dropping one of two same-named
servers would silently shadow the other's tools, which is the opposite failure.
Proven live in `v-mcp` (see Part M) and by three regression tests.

### F6 (defect, fixed): the redaction regex ate the token counts

`_SECRET_KEY` (`engine/trajectory.py:24`) matches the substring `token`, so it also
matches **`input_tokens`, `output_tokens`, `total_input_tokens`, `max_tokens`**.
Every per-response usage record on disk reads
`{"input_tokens": "[REDACTED]", "output_tokens": "[REDACTED]"}`.

**Scope, stated precisely** (an earlier draft of this finding overstated it): the
loop writes its own `usage` line *outside* redaction, so the totals were always
reconcilable - run `l5` reads `1284+1475 = 2759` in and `122+6 = 128` out, matching
the in-memory totals exactly. What was destroyed is the **copy inside the recorded
model response**, and with it any key containing the substring `token` in any
redacted payload. The blast radius is wider than usage: it is every field whose
name merely *contains* a secret word.

**Fixed** (`engine/trajectory.py`): the key pattern now matches **whole words** of
the key, normalized from camelCase and kebab-case first. `accessToken`,
`access-token`, `apiKey`, `client_secret` and `Authorization` are still redacted;
`input_tokens`, `max_tokens`, `tokens_used` and `auth_mode` now survive. Exposed as
`is_secret_key()` so the rule is testable directly, with a regression test over
both sets. Re-run live (`v-todo`): the response copy and the loop's own line agree
line by line, `4419` in and `392` out.

## Per-OS results

Legend: pass / fail / blocked / not run / **Not-Needed** (no OS-specific surface,
so a run adds no signal - always with its reason).

| | Linux | macOS | Windows native | WSL |
|---|---|---|---|---|
| Part L (loop contract) | Not-Needed | Not-Needed | Not-Needed | **run** |
| Part C (control-plane tools) | Not-Needed | Not-Needed | Not-Needed | **run** |
| Part R (crash + resume) | Not-Needed | Not-Needed | Not-Needed | **run** |
| Part P (policy) | Not-Needed | Not-Needed | Not-Needed | **run** |
| **Part N (desktop channel)** | **owed (0.4.x+)** | **owed** | **owed** | **run** (selection only) |
| **Part A (auth store)** | **owed (0.4.x+)** | **owed** | **owed** | **run** |
| Part M (MCP host) | Not-Needed | Not-Needed | Not-Needed | **run** |

**Two parts have a real per-OS surface, not one.** Parts L, C, R, P and M are pure
Python with no socket/pipe/path/registry/process branching and no per-OS deps, so
the other OSes **cannot** behave differently - that is `Not-Needed`, not `not run`.
**Parts N and A are different**: the desktop channel builds a different native
command per OS (`notify-send`/`zenity`, `osascript`, `powershell`) and the OAuth
store resolves per OS (Keychain vs file). This runbook proves the **selection** on
all four - the selection logic is injectable - but not that the selected command or
store actually works on macOS or native Windows. That is owed, and the
cross-platform round belongs in a later minor.

## What this runbook cannot prove

Stated so no reader mistakes a green table for a working product:

- **Nothing about the product's run path.** The engine is unwired at `0.4.0`; every
  part above drives it directly. Trigger-over-API and watch-over-WebSocket arrive
  with `0.4.1` and are proven in `E2E/0.4.1/e2e.md`.
- **Nothing about resume in production.** `resume()` and `find_latest()` are called
  from no non-test code, and `run_loop` has no resume entry point. Part R proves
  the library resumes correctly; it does not prove the daemon does. See F4.
- **Nothing about a real external MCP server.** `v-mcp` put an external server in
  a live run (the model discovered and called its tool) but it is an in-process
  stub. A real stdio/SSE server - handshake, subprocess lifetime, slow start,
  mid-run death - is owed with the first one that ships.
- **Nothing about the phone.** Mobile has never reached a machine; that is phase
  0's separate handset clause and mobile `0.4.0`.

## Open cells

Three, each with its reason - listed so nobody has to diff two versions to find
what is missing:

- **C5** `request_approval` **approve** branch: the goal-level task produced
  `ask_user` instead. Needs a task whose only sensible move is an approval.
- **C11** `ask_user` with `options`: the constrained-answer path.
- **R6** `idem` revalidation: not testable until resume is wired (F4).
