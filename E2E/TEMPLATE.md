# <version> - <what this minor made true>: e2e runbook

<One sentence: what a reader is being convinced of. Not what changed - what is
now demonstrably true that was not before.>

> **Status: <not started | partially run on \<OS\>, \<date\> | run on \<OS\>, \<date\>>.**
> Automated gate <green/red> (engine N, api N). <Which parts pass, which are
> open.> **N findings**, listed below. Nothing is marked pass that was not
> executed and read back.

<Copy this file to `E2E/<version>/e2e.md` and fill it in. Delete these angle
bracket notes as you go; a leftover placeholder is the tell that a runbook was
written and never run. The cross-cutting rules are in
[`../README.md`](../README.md) and are not repeated here.>

## Scope exception - **delete this section unless you need it**

<Only when the minor genuinely cannot be driven through a product surface. State
what is missing, that the runbook is therefore an **acceptance test** and not an
e2e, and the exact minor where the exception expires. `E2E/0.4.0` is the worked
example: the engine shipped as a library nothing called, so there was no surface
to drive, and the exception expired at `0.4.1`.

An exception is never "we did not have time". It is "there is no surface", and
it comes with a date.>

## The approach

Driven by a **real agent given a goal-level task**, per [`../README.md`](../README.md).
The verdict comes from `trajectory.jsonl` and the product's own responses, never
from the agent's prose.

Both surfaces are exercised and **neither substitutes for the other**:

- **the API + the run WebSocket** - how the phone calls it, and the only way to
  know a mobile call behaves;
- **the CLI** (`vadgr run`, `vadgr stream`) - the on-box path, with its own users
  and its own failure modes.

<The agent CLI invocation you actually used, so a reader can repeat it. Use
the CLI the machine has, and name it and its version beside the results; the
example is the `claude -p` form:>

```bash
claude --dangerously-skip-permissions --output-format stream-json --verbose -p \
  "<the goal-level task. Name a goal, never a call.>" \
  | tee /tmp/e2e-<version>.jsonl
```

## Prerequisites

<Everything a fresh machine needs, precisely enough to paste. Credentials,
env vars, a scratch runs dir so a test run never lands in `~/.vadgr/runs/`,
which port, which database.>

```bash
export AGENT_FORGE_DATABASE_PATH=$(mktemp -d)/vadgr.db
export AGENT_FORGE_PORT=8791
python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8791 &
```

## Automated gate (necessary, never sufficient)

<The suites, green, with counts. Then one line on what they cannot tell you -
because on every runbook so far, the defects were in the seams the unit tests
stop at.>

- `PYTHONPATH=. python3 -m pytest engine/tests/ -q` -> **N passed**
- `python3 -m pytest api/tests/ -q` -> **N passed**

## Coverage

<Only cells this minor can actually run. A check that needs something that does
not exist yet belongs in the runbook of the minor that builds it, not here as a
permanent `not run` - see [`../README.md`](../README.md). If you move one, say
so in a line here so the coverage stays traceable.>

<Deferred to a later minor, with where it went:>

| check | why it cannot run here | moved to |
|---|---|---|
| <...> | <the thing it needs that does not exist> | `<minor>` |


<Name the axes, multiply, write the number. If the product is large enough that
a full enumeration would not fit, say what you reduced and why - a silent
reduction reads as full coverage.>

| Part | Axes | Cells | Run | Open |
|---|---|---|---|---|
| <A> | <axis x axis> | N | N | N |
| | | **N** | **N** | **N** |

## Surface coverage - **every published endpoint, with what it returned**

<Not optional, and not a summary. A list of findings answers "what broke" and
never "what was checked" - and the second is what a reviewer is asking. Each row
carries **the response**, not a pointer to a file: nobody should open an artifact
to learn what an endpoint returned.>

<**Generate these from a recorded sweep. Never type them.** One harness drives
every surface and writes request, status, error code and body to a JSON record;
the tables are emitted from that record and both go in the evidence bundle. A
hand-written table drifts from the run it describes and nothing in it shows that.
`E2E/0.4.1` is the worked example - `sweep.py` and `gen_tables.py`.>

<Before trusting the harness, check it is real. Both of these silently recorded
nothing on the way to `0.4.1`: invoking the CLI as a module when the entry point
is the installed binary - it exits `0` printing nothing, so every command
"passes" - and letting the CLI use its default port while the daemon under test
is on another. **Assert on output, not only exit codes.**>

### Shipped

| endpoint | what was asked | status | code | response, as returned |
|---|---|---|---|---|
| `GET /api/...` | <the case> | `200` | - | `<the body>` |
| `POST /api/...` | negative: <the case> | `409` | `SOME_CODE` | `<the envelope>` |

<Assert the `code`, never the message: a client switches on one and shows the
other, so a wrong code is a divergence even when the status is right.>

### Not yet built - probed to confirm absent, not half-wired

| endpoint | minor | status | response |
|---|---|---|---|
| `POST /api/...` | `0.x.0` | `404` | `{"detail":"Not Found"}` |

<Worth the thirty seconds: one answering anything other than 404/405 was partly
wired, and that is a state nobody notices until a client calls it.>

### The CLI

| command | exit | output, as printed |
|---|---|---|
| `vadgr <cmd>` | `0` | `<the first lines, verbatim>` |
| `vadgr <cmd>` | `3` | `<the daemon-is-down case>` |

<Include at least one negative. Exit codes are what scripts branch on.>

### The sockets

| socket | frames | types, as received |
|---|---|---|
| `WS /api/...` | N | `{...}` |

## Part <X>: <what it proves>

| # | What | Expected | Status |
|---|---|---|---|
| X1 | <the check> | <the observable outcome, not "works"> | <pass / fail -> Fn / not run> |

**Measured.** <The actual output, pasted. Ids, counts, tokens, exit codes -
whatever a reader would need to disbelieve you with. A table of passes and no
evidence is a claim.>

```
<paste>
```

<One line on why this evidence is the right evidence. On this product it is
usually: the journal is the proof and the status is not, because a run ends
`completed` on the legacy path too.>

## Repeatability - **three independent passes**

<Three agents, concurrently, each with its own port, database and daemon. See
[`../README.md`](../README.md) for why isolation is what makes that safe, and
for what to compare.>

| | <port> | <port> | <port> |
|---|---|---|---|
| run | | | |
| HTTP entries | | | |
| CLI entries | | | |
| raw / mobile frames | | | |
| journal phases | | | |
| tokens in / out | | | |

<State explicitly what was diffed and that it matched: method/path/status/code,
argv/exit/output, frame counts - normalising only the run and agent ids.>

<**Input tokens should match; output tokens should differ.** Say so either way.
Three identical output counts are a warning that one result was reused, not
evidence of stability.>

<Anything an agent found odd that no assertion covered goes here or in Findings.>

## Evidence

<Where the artifacts for this runbook live, and the run ids that tie the two
together. Journals, frame captures and daemon logs go in the private repo - see
[`../README.md`](../README.md).>

The private evidence repo, under `e2e_evidence/<version>/`: journals per run
id, recorded frames, daemon logs, harnesses, and a `MANIFEST` of checksums.

## Findings

### F1 (<fixed | open>): <the defect in one line>

<What broke, the root cause at `file:line`, and why the tests did not catch it.
That last part is the one worth writing: a finding that says only "it was
broken" teaches nothing, and a finding that says "no unit test crossed this
seam" changes what gets tested next time.

If fixed: what changed and the test that now fails without it.
If open: why it is acceptable to ship, and the minor that closes it.>

## Per-OS results

Legend: pass / fail / blocked / not run / **Not-Needed** (no OS-specific
surface, so a run there adds no signal - always with its reason).

| | Linux | macOS | Windows native | WSL |
|---|---|---|---|---|
| Part <X> | | | | |
| Overall | | | | |

<Justify every `Not-Needed` in prose. "Pure Python, no socket/pipe/path/registry
/process branching and no per-OS deps, so the other OSes cannot behave
differently" is a reason. Silence is not, and neither is "it should be fine".

Anything touching the filesystem, spawning a process, resolving a credential
store, binding a port or drawing native UI is **owed**, not excused.>

## What this runbook cannot prove

<The honest limits, so nobody reads a green table as more than it is. Every
runbook has some; a runbook claiming none has not been thought about.>

- <...>
