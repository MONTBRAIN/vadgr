# E2E verification - read the journal, not the agent's words

Applies to **every** runbook in this directory (`E2E/<version>/e2e.md`).

An e2e is driven by a **real agent given a goal-level task**, never by a script.
A `.py` that imports `run_loop` and calls it directly is an **acceptance test**,
not an e2e - it proves the function works, not that the product does. The agent's
prose ("I started the run and it completed") is **self-report and is not
evidence**.

The operator invokes the public product surfaces exactly as a user does. Put
the tested installation on `PATH`, record `command -v vadgr`, prove that the
entry point targets the exact PR head, and run `vadgr ...` in the terminal. The
entry point can dispatch to Python during migration. The e2e cannot replace it
with `python -m cli`, a product import, `cargo run` or a private function call.
Exercise the public HTTP and WebSocket surfaces over their real wire as a
separate required half. A helper can prepare state, capture output and parse
evidence. It cannot drive the user flow or replace a product surface.

The trustworthy verdict comes from what the daemon wrote down, and vadgr has an
unusually good record for this: **`trajectory.jsonl`**, the run journal. The loop
writes it, not the model, so it can contradict the agent. **A claimed success
with no confirming journal line is a FAIL.**

## Where the ground truth is, in order of preference

**1. The run journal - the record.** One JSONL file per run:

```
~/.vadgr/runs/<run_id>/trajectory.jsonl
```

Written by the loop itself: a `response` line per model turn (with usage), and
for every tool call an `in_flight` line **before** dispatch and a `done`/`error`
line **after**. Secrets are redacted on write. This is the only artifact that
survives the process, and it is what a resume reads.

```bash
python3 - "$HOME/.vadgr/runs/$RUN_ID/trajectory.jsonl" <<'PY'
import json, sys, collections
recs = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
print("phases:", dict(collections.Counter(r.get("phase") for r in recs)))
for r in recs:
    if r.get("phase") == "in_flight":
        print("CALL", r["seq"], r["tool"], json.dumps(r.get("params", {}))[:120])
    if r.get("phase") in ("done", "error"):
        print("RSLT", r["seq"], r["phase"], json.dumps(r.get("result", r.get("error")))[:120])
    if r.get("phase") == "response":
        print("TURN", r.get("usage"))
PY
```

**2. The API and the database - what the product says happened.**
`GET /api/runs/{id}` for the terminal status, and the run row for what was
persisted. A status alone is weak evidence: a run ends `completed` on the legacy
CLI path too. **Pair it with the journal**, which only the native loop writes.

**3. The WebSocket streams - what watchers actually saw.** Use a real wire
client such as `websocat` or `wscat` against both
`/api/ws/runs/{run_id}` and `/api/runs/{run_id}/stream`. Needed for any claim
about frames reaching a client; a claim about `map_event` is a unit-test claim,
not an observation of the wire.

**4. The driving CLI's session transcript - the fallback.** When Claude Code
drove the run and its stream is not in your context, the tool calls are in
`~/.claude/projects/<sanitized-cwd>/<session-id>.jsonl`, one JSON object per
line, subagent turns marked `isSidechain: true`. When another CLI drove it, its
own session record serves the same way. The transcript cannot be edited by the
agent's summary.

## Driving a runbook with a subagent

One at a time **while they share a daemon** - two agents on one daemon read each
other's runs, and neither verdict means anything. Give each its own port,
database and daemon and they can run together; that is exactly what the
three-pass close below does. Goal-level task; the agent chooses its own calls.

Drive it with the agent CLI the machine has, Codex or Claude Code: detect it,
never assume it, and record the CLI and its version beside the result. The
example below is the `claude -p` form; translate the flags for the CLI you
have. Tee the stream so the verdict is reconstructable:

```bash
claude --dangerously-skip-permissions \
  --output-format stream-json --verbose -p \
  "You are testing vadgr 0.4.1 through its real surfaces.
   The daemon is on http://127.0.0.1:8791.
   Goal: start a run that plans some work and reports progress, watch it to
   completion, then tell me what the run's own journal says happened.
   Use the HTTP API and the vadgr CLI. Do not import the engine.
   Report the run id and the exact journal phases you observed." \
  | tee /tmp/e2e-0.4.1.jsonl
```

**The task names a goal, never a call.** "Start a run and watch it" tests the
product; "POST to /api/runs then GET /api/runs/{id}" tests your ability to write
curl.

## The verdict rules

- A run counts as having reached the **native loop** only if
  `~/.vadgr/runs/<run_id>/trajectory.jsonl` exists **at the API's own run id**
  and carries real `usage`. Status `completed` alone proves nothing.
- A **mutating action** counts only if an independent read-back confirms it - the
  journal, the filesystem, the database. Not the agent saying so.
- A **negative test** must show the failure arriving as data: an `error` line on
  that `seq`, a non-2xx with the contract's error envelope, a non-zero exit code.
  A silent success is a fail.
- **Resume counts only against a countable side effect that did not double.** A
  replayed run also ends `completed`, so "it finished after a restart" is not
  evidence of anything.
- Every frame a client receives must be one the published frame vocabulary
  names. A frame the phone has no case for is ignored silently, and the feature
  looks broken with nothing failing.
- If neither a journal nor a transcript is available, the test is **not
  verified** - say so. Do not infer a pass.

## Complete the runbook before the first live cell

Every surface branch and enum-shaped edge case is a separate executable cell
before credentials are spent or a daemon is started for live evidence. Each
cell has a stable id, precondition, setup, goal or action, expected observable,
independent oracle, evidence captured at its boundary, cleanup and result slot.
A prose list, an unmatched coverage count or a row called "remaining matrix"
is an unfinished runbook.

Put every owner-supplied prerequisite in one table before the cells: provider
keys, paid or quota-bearing accounts, operating-system hosts, devices,
applications, permissions, destructive actions and owner decisions. Map each
item to its cells, verify availability without printing secrets, and state cost
and cleanup. Inform the owner before the affected group starts. If an item is
unavailable, the written cells become `blocked`; they are never deleted,
collapsed or replaced with a smaller matrix after execution begins.

Provider keys come from the workspace `../.env` only. Never echo them or copy
them into commands, logs, screenshots, transcripts, process listings, GitHub
text, documentation or evidence. Run
`python3 scripts/check_no_secrets.py --env-file ../.env` before every commit and
before sealing evidence.

## A pass is finished, not paused

**Drive the whole matrix before reporting.** The failure this stops is not
laziness, it is a pass that stops at the first interesting result: partial
results look like progress, they get committed, and the cells that never ran
quietly stay never run. `0.4.7`'s Windows pass had to be restarted by the owner
several times for exactly this reason.

Three rules follow from it:

- **A blocked cell is owed only after its blocker was investigated.** On that
  pass a reserved port, a missing toolchain and an unbindable OAuth callback all
  read as immovable environment facts. All three were removable, and one of them
  was two daemons the pass had leaked itself.
- **Ask for the owner's part first and batch it.** A browser approval or an
  elevation prompt should be requested at the start and answered once, not
  discovered one cell at a time. Keep driving the unattended cells while it
  waits.
- **A fix that lands mid-pass invalidates the rows it touches.** Re-run those
  cells on every operating system that already passed them, because those
  results were observed against the old behaviour.

**And fix what you find.** A defect found by a runbook is repaired on the same
branch with a test that fails without it, and the cell is re-run until it
passes. Recording a defect and moving on is half the job.

## Test what this minor can test, and nothing more

A runbook covers **what is testable now**. A check that cannot be run because
the thing it needs does not exist yet **does not belong in this minor's
runbook** - it belongs in the runbook of the minor that makes it testable, and
it is written there when that minor is built.

This is not permission to skip hard checks. It is the opposite. An open cell
should mean *"we could have run this and have not yet"*, and it loses that
meaning the moment runbooks carry cells that were never runnable. Readers learn
that open cells are normal, start skimming them, and skim past the one that
actually mattered.

So before writing a cell, ask which it is:

- **Runnable now** - it goes in this runbook and it gets run. "The harness was
  awkward" is not a reason to leave it open; it is a reason to fix the harness.
- **Not runnable until minor N** - it goes in **N's** runbook, with one line here
  naming where it went, so the coverage is traceable rather than silently
  missing.

The tell that this rule is being broken: a cell whose "expected" column
describes a capability the code does not have. If a check needs a tool the loop
is not wired to, or a surface that ships two minors from now, it is not an open
cell - it is somebody else's cell.

## Enumerate the surface, never sample it

Name the axes, multiply them, write the cell count, and fill every cell or state
why it is open. That is the engineering standard; `E2E/0.4.0` is the worked
example (110 cells).

## Per-OS, and the honest use of `Not-Needed`

Every runbook ends with a per-OS table over **Linux / macOS / Windows native /
WSL**, because the daemon claims all four.

`Not-Needed` is a real verdict and it is **not** a synonym for "did not run". It
means the change has **no OS-specific surface** - no socket, pipe, path,
registry or process branching, and no per-OS dependency - so another OS
*cannot* behave differently and a run there adds no signal. Every `Not-Needed`
carries its reason.

Anything that touches the filesystem, spawns a process, resolves a credential
store, binds a port or draws native UI is **owed** on each OS, not excused. The
`0.4.0` runbook is the worked example of both: the loop and its tools are pure
Python and were `Not-Needed`, while OAuth token resolution and the desktop
channel branch per OS and were recorded as owed.

## Closing a runbook: three independent passes, three agents

A runbook is not finished on one green pass. Close it with **three separate
agents running the sweep concurrently**, each with **its own port, its own
database and its own daemon process**.

That is not a contradiction of "one at a time, never in parallel" above. That
rule exists to stop two agents sharing a daemon and reading each other's runs;
give each its own and the reason for it is gone. What concurrency then buys is
real: it rules out ordering effects and cross-run interference, which serial
repeats cannot.

**Compare them structurally**, normalising only the run id and the agent id:

- every HTTP entry on method, path, status and **error code**
- every CLI entry on argv, exit code and whether output was produced
- the frame type counts on each socket

**Then read the token counts, and expect them to disagree in one direction.**
Input should be identical across all three - the prompt and tool schemas are
fixed, so the input size cannot move. Output should differ, because a model's
prose is not deterministic. **Three identical output counts are a warning**:
they suggest a cached or shared result rather than three real calls. `0.4.1`
came back 2981 in on every run, and 81 / 83 / 85 out.

**Ask each agent what looked odd, not only whether its steps passed.** Every
status and exit code in `0.4.1`'s sweep was already correct when an agent
noticed the single unreachable-daemon case taking 15.2s against 0.1-0.8s for
every live call. No assertion could have caught it; nothing was asserting on
duration.

Practical: make the harness take the port as an argument rather than hard-coding
it, give each agent a work dir and the exact commands, and tell each to kill
**only its own** daemon by pid. A blanket `pkill uvicorn` takes the other two
runs down mid-flight.

## Coverage is a table, and it is generated

A runbook that lists findings has answered "what broke" and not "what was
checked". Both are needed, and the second is the one a reviewer is asking for.
Every runbook carries a table of **every published endpoint and every CLI
command**, and each row carries **the response that came back** - a reader
should not have to open an artifact to learn what an endpoint returned.

**Generate it from a recorded sweep; never type it.** One harness drives every
surface and records request, status, error code and body; the table is emitted
from that record. A hand-written table drifts from the run it describes and
nothing about reading it reveals that. `E2E/0.4.1` is the worked example.

**Check the harness is real before trusting it.** A sweep that records nothing
looks exactly like a sweep that passed. Two ways it happened here: invoking the
CLI as a module when the entry point is the installed binary, which exits `0`
having printed nothing, and letting the CLI talk to its default port while the
daemon under test is on another. Assert on output, not only on exit codes.

**Assert the error `code`, never the message.** A client switches on the code and
shows the message; a wrong code breaks the client even when the status is right.

## The artifacts live in the private repo

This runbook carries the plan and the results. The machine-written artifacts
behind them - run journals, recorded frames, daemon logs, the harnesses - go in
the private evidence repo under `e2e_evidence/<version>/`, because they carry
home paths, hostnames, ports and task prompts. The split is by content: a plan and a result are safe to
publish, a machine's fingerprints are not.

**Cite run ids here.** That is what ties the two together - a claim in this file
names a run, and the private bundle has that run's journal under the same id, so
any statement can be walked back to the file behind it. A runbook that says
"pass" without an id cannot be checked by anyone, including its author later.

Capture when the run ends, not when the PR is written: journals persist in
`~/.vadgr/runs/`, but frame captures and daemon logs usually sit in a scratch
directory that does not survive. Keep the runs that failed, keep both sides of
any fix that moved something observable, and if a run was never captured, say so
rather than reconstructing it.

## When a runbook finds a bug

Finding one is the point. Root-cause it in the source citing `file:line` - a
flaky environment is not a root cause until the code says so - fix it **on the
same PR branch** with a test that fails without the fix, re-run that part, and
record it as a numbered finding in the runbook. If the patch is released, add a
row to the patch log naming this runbook in the *found by* column.

**Start from [`TEMPLATE.md`](TEMPLATE.md).** Every runbook has the same shape so
a reader can find the verdict without learning a new document.
