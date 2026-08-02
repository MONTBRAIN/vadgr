# E2E verification — read the journal, not the agent's words

Applies to **every** runbook in this directory (`E2E/<version>/e2e.md`).

An e2e is driven by a **real agent given a goal-level task**, never by a script.
A `.py` that imports `run_loop` and calls it directly is an **acceptance test**,
not an e2e — it proves the function works, not that the product does. The agent's
prose ("I started the run and it completed") is **self-report and is not
evidence**.

The trustworthy verdict comes from what the daemon wrote down, and vadgr has an
unusually good record for this: **`trajectory.jsonl`**, the run journal. The loop
writes it, not the model, so it can contradict the agent. **A claimed success
with no confirming journal line is a FAIL.**

## Where the ground truth is, in order of preference

**1. The run journal — the record.** One JSONL file per run:

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

**2. The API and the database — what the product says happened.**
`GET /api/runs/{id}` for the terminal status, and the run row for what was
persisted. A status alone is weak evidence: a run ends `completed` on the legacy
CLI path too. **Pair it with the journal**, which only the native loop writes.

**3. The WebSocket stream — what a watcher actually saw.** `websocat` or
`vadgr stream`. Needed for any claim about frames reaching a client; a claim
about `map_event` is a unit-test claim, not an observation of the wire.

**4. The Claude session transcript — the fallback.** When a subagent drove the
run and its stream is not in your context, the tool calls are in
`~/.claude/projects/<sanitized-cwd>/<session-id>.jsonl`, one JSON object per
line, subagent turns marked `isSidechain: true`. The transcript cannot be edited
by the agent's summary.

## Driving a runbook with a subagent

One at a time, never in parallel. Goal-level task; the agent chooses its own
calls. Tee the stream so the verdict is reconstructable:

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
- A **mutating action** counts only if an independent read-back confirms it — the
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
  verified** — say so. Do not infer a pass.

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
means the change has **no OS-specific surface** — no socket, pipe, path,
registry or process branching, and no per-OS dependency — so another OS
*cannot* behave differently and a run there adds no signal. Every `Not-Needed`
carries its reason.

Anything that touches the filesystem, spawns a process, resolves a credential
store, binds a port or draws native UI is **owed** on each OS, not excused. The
`0.4.0` runbook is the worked example of both: the loop and its tools are pure
Python and were `Not-Needed`, while OAuth token resolution and the desktop
channel branch per OS and were recorded as owed.

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

Finding one is the point. Root-cause it in the source citing `file:line` — a
flaky environment is not a root cause until the code says so — fix it **on the
same PR branch** with a test that fails without the fix, re-run that part, and
record it as a numbered finding in the runbook. If the patch is released, add a
row to the patch log naming this runbook in the *found by* column.

**Start from [`TEMPLATE.md`](TEMPLATE.md).** Every runbook has the same shape so
a reader can find the verdict without learning a new document.
