# 0.4.1 - the engine on the production path: e2e runbook

Validation that a run **triggered through the product** reaches the native loop.

> **Status: partially run on WSL, 2026-07-31. Part A passes end to end.**
> Automated gate green (engine 116, api 536). Parts B, C and D are open and each
> says why. **Five defects found, all by this runbook and none by the unit
> tests**, which is the entire argument for running it before review.

## This is where `E2E/0.4.0`'s scope exception expires

`E2E/0.4.0/e2e.md` drove the loop by importing it, and said plainly that this
made it an acceptance test rather than an e2e, because the engine shipped as a
library nothing called. From this patch there is a product path, so the bar is
the one `ENGINEERING.md` §1a sets: drive the **real surfaces**.

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

## Part A: the API path

| # | What | Expected | Status |
|---|---|---|---|
| A1 | Daemon boots with resume-on-boot wired | healthy, no exception | **pass** |
| A2 | Create an agent on a native provider | reaches `ready` | **fail -> F5** |
| A3 | Trigger a run on `anthropic_oauth` | run reaches the **native loop** | **pass** |
| A4 | The loop actually ran | journal exists with real usage | **pass** |
| A5 | The journal is correlatable | journal dir == the API run id | **pass, after F4** |
| A6 | Terminal state | run ends `completed` | **pass** |
| A7 | The WS carries the loop's events | frames on `/api/ws/runs/{id}` | not run |
| A8 | The two dropped events never reach the socket | no `llm_response`/`tool_result` | not run |

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

## Part B: the CLI path - **not run**

`vadgr run` / `vadgr stream` against the same daemon. Owed, and it is not
optional: a green API run says the wire is right and nothing about the on-box
path.

## Part C: resume - **not run end to end**

Unit-covered (5 tests: clean journal skipped, dangling resumed, continues at the
uncompleted step, the service is told to continue, no journals is a no-op), and
**not proven on the product**. The honest version needs a real run with a
countable side effect, killed mid-flight, the daemon restarted, and the count
checked for a double. Until that runs, gate clause 2 stays unproven - which is
the same thing `E2E/0.4.0` said about the library, one layer up.

## Part D: the timeout - **not run**

That a native run outlives 900 seconds is asserted by construction (`timeout` is
`None` on the native path and the bridge ignores the parameter) and by a unit
test. A real multi-hour run is the dogfood spike's job, not this runbook's.

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

## What this runbook cannot prove yet

- **Nothing about the CLI path** (Part B).
- **Nothing about resume on the product** (Part C). Gate clause 2 remains proven
  at the unit level only.
- **Nothing about the WebSocket** (A7, A8), so the claim that the two unbounded
  events never reach a phone is currently a unit-test claim about `map_event`,
  not an observation of the socket.
