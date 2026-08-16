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

## Owner and environment requirements

<Complete this table before the first live cell. Tell the owner what is needed
before the affected group starts. Never print or persist a secret while checking
availability. A missing item blocks the already-written cells; it does not
remove them or reduce the matrix.>

<Read live credentials only from the workspace `../.env`. Never echo or copy a
value into a command, log, screenshot, transcript, process listing, GitHub text,
documentation or evidence. Run
`python3 scripts/check_no_secrets.py --env-file ../.env` before every commit and
before sealing evidence.>

| requirement | cells | non-secret availability check | cost or destructive effect | cleanup |
|---|---|---|---|---|
| <credential, billed account, OS/host, device, app, permission or decision> | <ids> | <present/absent check> | <none or exact boundary> | <action> |

## Billed model selection

<Complete this table from current official provider pages and the authenticated
catalog on the execution date. Pick the least expensive model that supports the
exact cell. An automatic onboarding model is tested once as shipped; repeated
provider-neutral tasks name an explicit cost-effective model. Do not start a
billed call with a blank ceiling or an unrecorded escalation path.>

| cells | provider/auth | required capabilities | selected model | official source and date | input/output price | hard iterations/tokens/cost | escalation condition |
|---|---|---|---|---|---|---|---|
| <ids> | <provider/method> | <endpoint, tools, content, continuation> | <authenticated id or snapshot> | <URL, YYYY-MM-DD> | <USD per MTok or subscription limitation> | <all three ceilings> | <recorded capability failure or none> |

<Test another model only for a distinct protocol/capability class or a
prewritten model-specific cell. Record actual tokens and calculated cost after
the group. Stop when any ceiling is reached.>

## Prerequisites

<Everything a fresh machine needs, precisely enough to paste. Credentials,
env vars, isolated state, config, database and runs roots so no test reads or
writes the owner's normal installation, which port and which transport. Name
every feature toggle the group relies on. Before the first live submission,
read the effective settings through the product surface and assert them. A
fresh database that inherits the owner's config is not isolated.>

```bash
export AGENT_FORGE_DATABASE_PATH=$(mktemp -d)/vadgr.db
export AGENT_FORGE_PORT=8791
python3 -m uvicorn api.main:app --host 127.0.0.1 --port 8791 &
```

## Remote-host handoff for Linux, macOS and Windows

<Complete this section before any native-platform group runs. It must let a new
Codex session execute the group without hidden context or access to the first
test machine. Include all of these items:>

1. <Files to read first: `AGENTS.md`, `E2E/README.md`, this runbook, and any
   public install instructions.>
2. <The exact PR head rule, release build command, delivered artifact path,
   artifact hash command, and installation into an empty host-local test root.
   The product under test is the installed release copy, never `cargo run`.>
3. <The exact installed `vadgr-computer-use` version, fresh-environment install
   command, `vadgr-cua doctor` check, and platform setup. Include Linux
   `install-deps`, macOS Accessibility and Screen Recording, and native Windows
   execution without WSL.>
4. <The isolated state, config, database, runs, evidence, port, transport,
   feature toggles, `VADGR_CUA_BIN` and API URL variables for Unix shells and
   native Windows PowerShell. Use native platform directory and access-control
   APIs. Assert the effective settings through the installed product before a
   live task.>
5. <The exact cell ids and order for each host, state carried between cells,
   independent read-backs, evidence captured before cleanup, and result rows
   that host updates.>
6. <Cleanup boundaries. Remove only the isolated root and reversible effects.
   Never stop unrelated processes or applications.>
7. <Credential handling. Read only required values from the owner-only
   workspace `../.env`; never print or persist them. Run the secret check before
   the group and before evidence is sealed.>

<Provide paste-ready Linux/macOS shell and Windows PowerShell blocks. Use a free
loopback port per concurrent pass. A platform row with only "run the same test"
is incomplete.>

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

<Every counted case is a row before execution. Its Status column is the result
slot. Do not use aggregate placeholders such as "remaining matrix" or leave
edge cases in prose.>

| # | Precondition and setup | Goal or action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| X1 | <state and setup> | <goal-level task or action> | <observable result and independent machine oracle> | <files/records captured now> | <restore/remove> | <pass / fail -> Fn / blocked: reason / not run> |

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
