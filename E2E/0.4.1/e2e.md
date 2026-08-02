# 0.4.1 - the engine on the production path: e2e runbook

Validation that a run **triggered through the product** reaches the native loop.

Format and verification rules: [`../README.md`](../README.md) and
[`../TEMPLATE.md`](../TEMPLATE.md).

> **Status: run on WSL, 2026-08-02. Parts A and B pass end to end, and C clause 1 with them.**
> Automated gate green (engine 122, api 548). **Every published endpoint that is
> shipped was driven and is in the coverage table below**, along with the ten
> that are not yet built and answered `404`/`405` as they should. Part C's
> gate-park path and Part D are **not testable at this minor** and have moved to
> the runbooks that can run them. **Thirteen defects found, all by this runbook
> and none by the unit tests**, which is the entire argument for running it
> before review.

## This is where `E2E/0.4.0`'s scope exception expires

`E2E/0.4.0/e2e.md` drove the loop by importing it, and said plainly that this
made it an acceptance test rather than an e2e, because the engine shipped as a
library nothing called. From this patch there is a product path, so the bar is
the one the engineering standard sets: drive the **real surfaces**.

There are two and **neither substitutes for the other**:

- **the API + the run WebSocket** - how the phone calls it, and therefore the
  only way to know a mobile call behaves;
- **the CLI** (`vadgr run`, `vadgr stream`) - the on-box path, with its own users
  and its own failure modes.

## What the automated gate cannot tell you

The unit suite was green - 15 bridge tests, 5 resume tests, 116 engine - while
**every agent on the native provider went to status `error` at creation** and the
wiring was unreachable. Nothing was wrong with the bridge. The failures were all
on the path between the API and it, which no unit test crossed.

That is the finding worth carrying: a seam is exactly where unit tests stop.

## What this minor cannot test, and where it went

Per [`../README.md`](../README.md), a check that cannot run because the thing it
needs does not exist yet belongs to the minor that builds it. Two moved out, and
both moved because of a missing surface rather than a missing afternoon:

| check | why it cannot run here | moved to |
|---|---|---|
| A gate parks, the daemon is killed, resume continues it | The daemon wires `CLIChannel`, which reads a stdin it does not have, so **no gate can hold open on the API path at all** (F11). The shipped `/approve` cannot close the gap: it carries no answer text, and its resume replays | `0.5.0`, with `POST /api/runs/{id}/respond` |
| A native run outlives 900s | A real multi-hour run is not a runbook check. It is the dogfood spike's whole job | the dogfood spike |

Both were previously carried here as open cells, which is the habit the rule
exists to break: an open cell has to keep meaning "runnable, not yet run".

Resume itself is **not** deferred - clause 1 (a clean journal is correctly
unresumable) is proven below. It is clause 2, the dangling record, that needs a
gate that can park.

## Surface coverage - every published endpoint, and its verdict

The findings below say what broke. This says what was **checked**, which is the
question a table of findings cannot answer. Every endpoint the published
reference lists as shipped, driven live on WSL against the daemon on `8791`:

| endpoint | exercised | status | error code | verdict |
|---|---|---|---|---|
| `GET /api/health` | CLI and curl | `200` | - | **pass** - status, version, modules |
| `GET /api/providers` | curl | `200` | - | **pass** - `anthropic_oauth` available, catalogue current |
| `GET /api/devices` | curl | `200` | - | **pass** - `[]`, no device paired |
| `DELETE /api/devices/{id}` | unknown id | `404` | `DEVICE_NOT_FOUND` | **pass** |
| `POST /api/auth/pair` | loopback transport | `503` | `TRANSPORT_UNREACHABLE` | **pass, after F13** - correct refusal: a `127.0.0.1` QR is useless to a phone |
| `POST /api/auth/claim` | wrong code | `401` | `PAIRING_CODE_INVALID` | **pass, after F13** |
| `POST /api/agents/{id}/run` | 6 runs, native provider | `202` | - | **pass** - reaches the loop, journal at the API's own run id |
| `GET /api/runs` | CLI `runs list` and curl | `200` | - | **pass** |
| `GET /api/runs/{id}` | curl | `200` | - | **pass** - terminal status |
| `GET /api/runs/{id}` | unknown id | `404` | `RUN_NOT_FOUND` | **pass** |
| `GET /api/runs/{id}/outputs/{f}` | prose output | `200` | - | **fail -> F12, fixed.** Was `500` |
| `GET /api/runs/{id}/outputs/{f}` | unknown field | `404` | `OUTPUT_NOT_FOUND` | **pass** |
| `POST /api/runs/{id}/cancel` | finished run | `409` | `RUN_NOT_ACTIVE` | **pass** - refuses, with the envelope |
| `POST /api/runs/{id}/resume` | completed run | `409` | `RUN_NOT_RESUMABLE` | **pass** |
| `WS /api/runs/{id}/stream` | recorded, whole run | - | - | **fail -> F9, fixed.** 2 frames, then 11 |
| `WS /api/ws/runs/{id}` | recorded, whole run | - | - | **pass, after F7** - authed, send-only, loopback tokenless |

**Codes are the contract; messages are prose.** Every negative case above was
checked on its `code`, not its sentence: a client switches on one and shows the
other, so a wrong code is a divergence even when the status is right. F13 is
exactly that failure - two right statuses carrying two wrong codes.

**Not yet built, and correctly absent.** Probed anyway, because a future
endpoint answering something other than `404`/`405` means it was half-wired,
which is the state nobody notices until a client calls it:

| endpoint | minor | observed |
|---|---|---|
| `GET /api/machine` | `0.5.0` | `404` |
| `PATCH /api/machine` | `0.6.0` | `404` |
| `POST /api/runs` | `0.5.0` | `405` |
| `POST /api/runs/{id}/pause` | `0.5.0` | `404` |
| `POST /api/runs/{id}/respond` | `0.5.0` | `404` |
| `GET /api/runs/{id}/journal` | `0.5.0` | `404` |
| `POST /api/runs/{id}/messages` | `0.6.0` | `404` |
| `GET /api/threads` | `0.6.0` | `404` |
| `GET /api/approvals` | `0.7.0` | `404` |
| `PUT /api/devices/{id}/push_token` | `0.7.0` | `404` |

All ten absent, none half-wired.

**One endpoint is deliberately still here**: `POST /api/agents/{id}/run` is
replaced by `POST /api/runs {task}` at `0.5.0`. It is the path this minor wires
the loop onto, so it is tested as shipped rather than as deprecated.

## Part A: the API path

| # | What | Expected | Status |
|---|---|---|---|
| A1 | Daemon boots with resume-on-boot wired | healthy, no exception | **pass** |
| A2 | Create an agent on a native provider | reaches `ready` | **fail -> F5** |
| A3 | Trigger a run on `anthropic_oauth` | run reaches the **native loop** | **pass** |
| A4 | The loop actually ran | journal exists with real usage | **pass** |
| A5 | The journal is correlatable | journal dir == the API run id | **pass, after F4** |
| A6 | Terminal state | run ends `completed` | **pass** |
| A7 | The WS carries the loop's events | frames on `/api/ws/runs/{id}` | **pass** |
| A8 | The two dropped events never reach the socket | no `llm_response`/`tool_result` | **pass** |
| A9 | Every frame emitted is one the published vocabulary names | no invented frame reaches the phone | **pass, after F10** |
| A10 | The phone's stream carries the run, not just its ends | frames between `started` and `completed` | **fail -> F9, fixed** |
| A11 | A declared checklist reaches the wire | a `todos` frame with parseable items | **fail -> F8, F10, fixed** |

**A9 was a real gap, found by checking the code against the contract rather than
against itself.** The bridge mapped the loop's checklist to a `todos` event and
the executor's `if/elif` had no branch for it, so the frame died one layer below
the bridge and the phone could never receive a checklist - exactly what
the API reference predicted when it said the mockups draw one the API cannot
deliver. The gate frame was also named `awaiting_approval` where the contract
says `awaiting`, which would have been a rename paid for twice, once here and
once in the client. Both fixed, and a test now asserts the bridge emits nothing
the contract does not name.

**Measured (A3-A6).** `POST /api/agents/{id}/run` with
`{"provider":"anthropic_oauth","model":"claude-opus-5"}`:

```
api run id            9e514a92-03a1-48a4-aee6-9ae5a63cf3aa
journal at that id    YES        (~/.vadgr/runs/9e514a92-.../trajectory.jsonl)
run status            completed
run provider          anthropic_oauth
journal phases        {'response': 1}
usage                 input 1452, output 4
```

The **journal is the proof**, not the status. A run can end `completed` on the
old CLI path too; only the native loop writes `trajectory.jsonl`, and the token
usage in it is a real model call rather than a subprocess's stdout.

**Measured (A7-A11).** One run, both sockets recorded verbatim, checked against
the journal for the same run. Run `4abb32cf`:

```
raw    /api/ws/runs/{id}       run_started 1  agent_started 1  agent_log 7  todos 1  agent_completed 1  run_completed 1   = 12
mobile /api/runs/{id}/stream   started 1  tool_call 1  output 8  completed 1                                              = 11
journal                        response 4   in_flight 4   done 4

A8  "llm_response" as a frame type on either socket   0     (as a substring anywhere in the capture: 0)
    "tool_result"  as a frame type on either socket   0     (as a substring anywhere in the capture: 0)
    model turns the journal records                   4     -> 4 llm_response events occurred, 0 reached the wire
    tool results the journal records                  4     -> 4 tool_result  events occurred, 0 reached the wire
A9  raw frames outside the published vocabulary       none
    mobile frames outside RunEventType                none
A11 todos payload is a list of dicts                  True
```

**This is why A8 had to run rather than be argued.** The claim is not "`map_event`
returns `None` for two types" - that is a fact about a function and a unit test
already had it. The claim is that those events **never reach a client**, and the
journal is what makes the run admissible evidence: it records 4 model turns and 4
tool results, so both event types demonstrably occurred, and the capture shows
neither on either socket. A run where they had not happened would have proven
nothing.

Loopback still connects with no token, so F7's auth fix did not close the socket
to the on-box path - the same property B3 proves for the CLI.

**A10 and A11 are what running it bought.** Before the fixes the mobile stream
carried **2 frames for a 6-tool-call run**: `started`, then silence, then
`completed`. After, 11. That gap is invisible to every test that asks "does the
translator translate", because the translator was translating correctly - it was
translating names nothing sends.

## Part B: the CLI path - **passes**

| # | What | Expected | Status |
|---|---|---|---|
| B1 | `vadgr health` reaches the daemon | status, version, modules | **pass** |
| B2 | `vadgr runs list` | the runs Part A created | **pass** |
| B3 | `vadgr run <agent>` triggers **and watches** | run completes, exit `0` | **pass** |
| B4 | The CLI-triggered run reached the native loop | journal at the API run id | **pass** |

**Measured (B3-B4):**

```
[vadgr] Run started: e5e0dbb3-3274-48bf-a378-94b8fd9c82ac
[vadgr] Run completed (2s)
exit 0

journal at that id   YES        usage   input 1452, output 4
```

The CLI watches over `/api/ws/runs/{id}`, which this patch **authenticated** -
so B3 also proves the auth fix did not break the on-box path, which was the
risk in touching it.

## Part C: resume - **clause 1 proven, clause 2 moved to `0.5.0`**

Unit-covered (5 tests). On the product, the two clauses split:

**Clause 1 - a clean journal is correctly unresumable. Proven.** A run whose
tool calls all closed leaves no dangling `seq`, `find_latest` returns nothing,
and nothing is resumed. That is the right behaviour and not a null result: a
resume that replayed a finished run is the failure this clause exists to
exclude.

**Clause 2 - a dangling record is continued, not replayed. Moved to `0.5.0`.**
It needs a run killed *inside* a call that is waiting, and the only tool that
waits is a gate. Three attempts, and the third finally said why:

1. The run finished its calls faster than the kill landed - clean journal, see
   clause 1.
2. The gate could not park at all: `TypeError` on a timeout the model typed as
   `"300"`. That is **F6**, fixed here.
3. With F6 fixed the gate **did** park - and died 3ms later on
   `EOF when reading a line`. That is **F11**, and it is not a harness problem.

F11 means no gate can park on the API path at all, so there is no state on this
minor that a kill could interrupt. Under the runbook rule this stops being an
open cell and becomes `0.5.0`'s, because the fix is an API channel resolved by
`POST /api/runs/{id}/respond` - an endpoint that does not exist yet.

```
seq 0  in_flight  control__report_progress  {"message": "MARKER-ONE"}
seq 0  done       {"ok": true}
seq 1  in_flight  control__ask_user         {"question": "Which folder should I use?", "timeout": 600}
seq 1  await_user {"kind": "question", ...}          <- parked, so F6 is genuinely fixed
seq 1  error      "EOF when reading a line"          <- 3ms later. F11
```

Note the timeout: `600`, sent as a number. F6's fix is why this run got as far
as parking at all.

## Evidence

The private evidence repo, under `e2e_evidence/0.4.1/`: eleven run journals
keyed by the run ids this file cites, both socket captures either side of the F9 and F10 fixes, daemon
logs, the two harnesses, and a `MANIFEST` of checksums. The failed runs are kept
alongside the passing ones: `f9a7b824` is F8 in the product's own handwriting,
and `f67cb5fe` is F11's park-then-EOF three milliseconds apart.

## Findings

### F1 (fixed): a native provider had no `args`, so agent creation raised

`load_provider_config` did `config["args"] + ["--model", model]`. A native
provider has a `module`, not an argv. `KeyError: 'args'`.

### F2 (fixed): `ProviderConfig` required a `command`

Same root cause one level down: the dataclass made `command` mandatory, so
loading a native entry raised `TypeError`. It now defaults to empty, which is
what a native provider honestly has.

### F3 (fixed): the availability check spawned an empty argv

`is_available()` fell through to `create_subprocess_exec()` with `''` and raised
`PermissionError: [Errno 13] Permission denied: ''`. A provider with no command
is the in-process engine and is always available: there is nothing to find on
PATH and nothing to spawn.

**F1, F2 and F3 are one defect wearing three hats**: nothing on the creation path
knew that a provider might not be a subprocess. Each was invisible to the unit
tests because each is in code the bridge does not call.

### F4 (fixed): the journal could not be tied to the run

The executor never passed `run_id` to `execute_streaming`, so the loop minted its
own and wrote `~/.vadgr/runs/run-c02c2fa8c7f5/` for API run
`628ceccf-d34d-...`. Two consequences, and the second is worse than a cosmetic
mismatch: nothing could correlate a journal with the run it belongs to, and
**resume-on-boot was broken** - it finds a journal by id and then looks that run
up, which would never have matched.

### F5 (open, and a scope discovery rather than a bug)

**Agent creation is CLI-bound and this patch does not change that.** `POST
/api/agents` runs *forge generation*, which spawns the configured provider as a
subprocess to generate the agent's files. A native provider cannot do that, so an
agent created directly on `anthropic_oauth` still ends in status `error`.

It does not block `0.4.1`, because a **run** may override the provider
(`{"provider": ..., "model": ...}` on the trigger, and the API requires them
together), which is the path Part A exercised. But it means the native loop is
reachable per-run and not yet as an agent's own provider, and that is worth
saying out loud rather than discovering at `0.5.0`. The reshape replaces this
path with `POST /api/runs {task}`, where the question disappears - a free-form
run has no forge generation.

### F6 (fixed): a gate raised instead of asking, on a timeout the model typed

`ask_user` and `request_approval` declare `timeout` as a JSON Schema `number`,
and a JSON Schema type is **advisory** - the value arrives as whatever the model
emitted. It emitted `"300"`. `asyncio.wait_for` then compared a `str` to an
`int` and raised `TypeError: '<=' not supported between instances of 'str' and
'int'`.

The failure mode is the worst available to a human-in-the-loop tool: **the run
failed at the exact moment it was trying to consult a human.** Not a park, not a
refusal - a crash, where the whole point of the tool is that a human gets asked.

Timeouts are now coerced, and an unparseable one means no timeout rather than an
exception. This is the same class as `0.4.0`'s F3, where the model wrote
`completed` for a status whose enum said `done`: **a schema enum or type is a
hint to the model, never a guarantee to the runtime**, and every value crossing
that boundary has to be treated as untrusted input.

### F7 (fixed): the on-box WebSocket authenticated nothing

`/api/ws/runs/{run_id}` never called the authorizer - the auth middleware is
HTTP-only - so any peer gate 1 admits could open it, which over a tailnet is
every member of it. It also honoured an inbound `approval_response` that resumed
a parked run, making it an **unauthenticated way to answer a human-approval
gate**: the one decision the entire gate layer exists to protect.

Both fixed here rather than at `0.5.0`, because the hole goes live the moment a
phone reaches a machine over a tailnet, which is mobile `0.4.0`. The socket now
authenticates exactly as `/stream` does and is **send-only**; answering is
`POST /api/runs/{id}/respond`, which is authenticated, idempotent and auditable.
The route is still deleted at `0.5.0` - it has a live consumer today (the CLI,
`cli/stream.py`), and B3 proves the fix did not break it.

### F8 (fixed): a checklist sent as a JSON string crashed the tool

`todo_write` did `args.get("items", [])` and iterated it. The model sent `items`
as a **string containing JSON** - three times in one run, in three different
formattings - and iterating a `str` yields characters, so every entry reached
`_normalize` as a one-character string: `'str' object has no attribute 'get'`.

The file already knew better one line down. `engine/tools/todo.py:15` says a
JSON-Schema enum is advisory and maps the synonyms a model reaches for. The same
reasoning was simply never applied to the **container**: the schema declares
`items` an `array`, and that declaration is exactly as advisory as the enum.

This is the third instance of one lesson - `0.4.0`'s F3 (`completed` for a status
whose enum said `done`), F6 (`"300"` for a `number`), and now the array itself.
**A schema is a hint to the model, never a guarantee to the runtime**, and it
holds for types and containers, not only for enum values.

The consequence is what makes it worth the fix rather than a note: A9 had just
taught the bridge to carry a `todos` frame, and **the tool that produces it
raised on the shape the model actually sends**. The plumbing was fixed and the
tap above it was broken, so the checklist could never have arrived.

### F9 (fixed): the phone's stream carried a run's start and end and nothing between

`_EVENT_TYPE_MAP` in `api/routes/ws.py` named eight internal event types. **Five
of them are emitted by nothing** - `step_started`, `tool_call`, `step_output`,
`output`, `approval_required` - while the executor's real vocabulary
(`agent_log`, `agent_started`, `agent_completed`, `awaiting`, `agent_failed`)
was absent. Only the three run-level frames mapped.

So a phone watching a run received `started`, silence, `completed`, however long
the run and however much it reported. Measured before the fix: **2 frames for a
six-tool-call run.** After: 11.

The severe half is `awaiting`. That is how a gate says it is waiting for a human,
and with no mapping **an approval request could never reach the device that has
to answer it** - the gate layer's entire purpose, unreachable through a mapping
table.

`vadgr-mobile` has a `RunEventKind.toolCall` case for a frame the server never
sends, which is the no-dead-controls rule's dead control one layer down in the data.

Pre-existing rather than introduced here (`9b0883f`), and the API reference had
already flagged the `todos` corner of it - "the phone cannot receive this today".
It is fixed here because this runbook is what turned a footnote about one frame
into a measurement showing it was all of them. The fix is the mapping only; new
frame types are `0.5.0`'s enrichment, and inventing them here would be a rename
paid for twice.

A test now asserts every key in the map against the strings `executor.py` really
broadcasts, because nothing raises when a map names an event nobody sends.

### F10 (fixed): the checklist reached the wire as a Python repr

With F8 and F9 fixed the `todos` frame finally arrived - carrying
`"[{'id': '1', 'content': ...}]"`. Single quotes. A `str()` of a list, which is
not JSON and not the `{items:[{id,content,status}]}` the published payload shape promises.

`ExecutionEvent.data` was annotated `str`, so `native_bridge.py` coerced the
checklist to fit the field with the first coercion to hand.

**This is the one that indicts A9's test rather than the code.** A9 asserts the
bridge emits no frame *type* the contract does not name, and it passed
throughout - a type assertion cannot see a payload shape. The frame was correctly
named and unparseable by anything receiving it. Found only because the wire was
read, which is the whole argument for A7 being a cell rather than a unit test.

### F11 (open, closes at `0.5.0`): no gate on the daemon can reach a human

`_anthropic_base.py:90` builds the default router as `{"cli": CLIChannel(),
"desktop": DesktopChannel()}`, active `cli`. `CLIChannel` reads **stdin**, and
the daemon is a background service with none. Every gate on the API path parks
and dies ~3ms later on `EOF when reading a line`.

Same shape as F6 and worse: F6 was a crash on a typed value and this is
structural. `ask_user`, `request_approval` and the plan gate are all reachable,
all park correctly, and **none of them can ask anyone.**

**Deferred to `0.5.0`, and the shipped endpoint is why rather than a missing
one.** `POST /api/runs/{id}/approve` exists today, so "there is nowhere to
answer" would be false. It fails on two specifics instead:

- **It carries a verdict and no text.** The route takes no body. `request_approval`
  is binary and would fit; `ask_user` and `propose_plan` need an answer, and two
  of the three gates cannot be served by a yes.
- **Its resume replays.** `resume_after_approval` calls `run_project` - the DAG
  path, not the native loop - whose own comment says re-running the full project
  is acceptable for MVP. Continuing the loop through it would mean building on a
  mechanism that does the one thing the journal exists to prevent.

`0.5.0`'s `POST /api/runs/{id}/respond` is shaped for this: a verdict, a reason
and an answer, resolving against the loop's own resume. `respond` already
replaces `approve`, so this is the minor doing its job
rather than a gap. Wiring the native loop into the deprecated route would be
work deleted one minor later, and it would carry the replay in with it.

What did change is the error. `EOF when reading a line` describes a file
descriptor; the model reads that string and retries a gate that cannot succeed.
It now says there is no interactive channel and to proceed or stop rather than
retry - true, actionable, and no new surface.

It does not block `0.4.1`, whose claim is that a run reaches the native loop.
It does block calling the gate layer usable from the product, and Part C clause 2
with it.

### F12 (fixed): an output field of prose answered `500`

`GET /api/runs/{id}/outputs/{field}` hands the output value to `Path.resolve()`
to see whether it names a file on disk. An output field holds whatever the run
produced, and since the native loop that is usually the model's prose - so past
`NAME_MAX` (255 bytes) `resolve()` raised `OSError: File name too long` and the
route answered `500` with FastAPI's bare body.

This route has exactly two outcomes, the artifact bytes or `404`, so `500` is
not one of them. It was broken for **essentially every free-text output**, which
is the common case on this path and became the common case *because* of this
minor: before the native loop, outputs were file paths from forge generation.

Values that cannot be a path are treated as text, and `resolve()` is guarded for
what the length check does not cover. The test uses the actual 438-byte output
that caused it, taken from run `4abb32cf`'s journal.

Found by probing the published surface rather than by a run, which is the
argument for the coverage table above existing at all: no runbook cell pointed
at this endpoint, and no unit test called it with a realistic value.

### F13 (fixed): two right statuses carrying two wrong codes

Pairing refused correctly and named itself wrongly:

| | returned | published |
|---|---|---|
| loopback transport | `503 TRANSPORT_UNAVAILABLE` | `503 TRANSPORT_UNREACHABLE` |
| bad pairing code | `401 INVALID_PAIRING_TOKEN` | `401 PAIRING_CODE_INVALID` |

**Codes are the contract; messages are prose.** A client switches on the code
and shows the message, so a wrong code is a live divergence even though both
statuses were right and both messages were sensible. The phone codegens that
switch, and this is the **first-run flow** - the one screen every owner sees.

A third gap came with it. The published errors distinguish `410
PAIRING_CODE_EXPIRED` from `401 PAIRING_CODE_INVALID`, and the reason is
written down: the phone tells the owner to ask for a new code rather than that
they mistyped this one. `PairingStore.consume()` returned a bare `bool`, so the
two collapsed. It now returns a reason, and the route answers `410`.

Fixing that surfaced a second-order bug **in the fix**, caught by its own test:
the store swept expired tokens *before* the lookup, so redeeming any token
purged every other expired one and turned their verdict from expired into
unknown. The distinction existed and did not survive being asked for. Sweeping
moved to `mint()`, the only moment the store grows.

Still absent: `429 RATE_LIMITED` on both pairing routes. The store has no
attempt counter, so the published five-attempt burn is unimplemented. Low risk -
an 8-character Crockford base32 code inside a five-minute window is not
practically guessable over HTTP - but it is specified behaviour that does not
exist, so it is named here rather than discovered later.

## Per-OS results

Legend: pass / fail / blocked / not run / **Not-Needed** (no OS-specific
surface, so a run there adds no signal - always with its reason).

| | Linux | macOS | Windows native | WSL |
|---|---|---|---|---|
| Part A (the API path) | Not-Needed | Not-Needed | Not-Needed | **pass** |
| Part B (the CLI path) | Not-Needed | Not-Needed | Not-Needed | **pass** |
| Surface coverage (every shipped endpoint) | Not-Needed | Not-Needed | Not-Needed | **pass** |
| Part C clause 1 (a clean journal) | **owed** | **owed** | **owed** | **pass** |
| Part C clause 2 (a dangling record) | moved to `0.5.0` | moved to `0.5.0` | moved to `0.5.0` | moved to `0.5.0` |
| Overall | Not-Needed except C1 | Not-Needed except C1 | Not-Needed except C1 | **A, B, C1 pass** |

**A and B are `Not-Needed` elsewhere**: the bridge is a queue and a mapping
table, provider selection reads a YAML key, and the timeout is a parameter that
is not passed. Pure Python, no socket, pipe, path, registry or process
branching, and no per-OS dependency - the other three OSes **cannot** behave
differently.

**Part C clause 1 is owed on every OS**, and that is the one row that is not an
excuse. Resume reads `~/.vadgr/runs/` and turns on the daemon dying and being
restarted, which is filesystem behaviour plus process lifecycle - the two things
that genuinely differ across platforms. A journal path resolves differently on
Windows, and what a killed process leaves half-written is not the same on NTFS
as on ext4. It cannot be reasoned about from a WSL run, so it is owed rather
than `Not-Needed`.

## What this runbook cannot prove yet

- **That a dangling journal record is continued rather than replayed.** Proven at
  the unit level (5 tests) and not on the product, because F11 means nothing can
  park long enough to be interrupted. It is `0.5.0`'s cell now, and the phase
  cannot close until it is run there.
- **That the gate layer works end to end.** Gates park correctly and reach nobody
  (F11). Everything this runbook says about gates is about the parking half.
- **That a run survives a long horizon.** The 900s timeout is absent by
  construction and unit-tested; a real multi-hour run is the dogfood spike's.
- **That the frames are the right frames for a phone.** A7-A11 prove the ones
  emitted are named by the contract, arrive, and parse. Whether the phone renders
  a run well from them is mobile's runbook, not this one.
- **Anything about resume across filesystems.** Clause 1 ran on WSL only; a
  killed process leaves different debris on NTFS than on ext4.
