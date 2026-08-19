# <version> - <what this minor made true>: e2e runbook

<One sentence: what a reader is being convinced of. Not what changed - what is
now demonstrably true that was not before.>

> **Status: <not started | partially run on \<OS\>, \<date\> | run on \<OS\>, \<date\>>.**
> Automated gate <green/red> (engine N, api N). <Which parts pass, which are
> open.> **N findings**, listed below. Nothing is marked pass that was not
> executed and read back.
> The header, the coverage counters and the per-OS table are re-read against
> the cell marks before the runbook is offered: a file that says `not started`
> over cells that say `pass` is wrong twice, and a reader cannot tell which
> half to believe. Count the rows, then read the counters against them.

<Copy this file to `E2E/<version>/e2e.md` and fill it in. Delete these angle
bracket notes as you go; a leftover placeholder is the tell that a runbook was
written and never run. The cross-cutting rules are in
[`../README.md`](../README.md) and are not repeated here.>

## The rules

**Read this before the first cell.** Every rule here was learned by breaking it,
they hold on every supported operating system and for every driver of a runbook,
and none of them is negotiable against a deadline or a token budget.

**This list is an index, not the rules themselves.** Each entry is deliberately
short. A bracketed name is where the rule is stated in full, with the incident
that produced it: a section of this file, or `../README.md`. Read the entry
before you start and the section when it bites. Where a bracketed name is not
present in a given runbook, the entry is all there is.

1. **Whatever needs the owner runs first.** Read the whole matrix, list every
   cell that cannot proceed without a human, and run those cells before any
   unattended one. **Running them is the rule; announcing them is not.**
   [How a pass is run] [../README.md]

2. **Do not stop the pass to report.** The pass runs to completion for the
   operating system it is on, and what it finds is written down as it happens and
   reported at the end. [How a pass is run] [../README.md]

3. **A bug you find is a bug you fix, here and now, with a test that fails
   without the fix.** Re-run the failing cell until it passes and push to the
   pull request branch before carrying on. [How a pass is run] [../README.md]

4. **A fix invalidates the cells it touched on every operating system that passed
   them**, so name them, mark them `not run` and re-run them. **A rebuild is a
   new subject**: re-run the identity cell and record the new hashes before any
   further cell. [How a pass is run]

5. **The evidence is pushed, not left on the machine that produced it, and it is
   pushed to the private docs repository** under `e2e_evidence/<repo>-<minor>/`,
   never into this one. The pull request carrying it is opened there as part of
   the pass, not after somebody asks. [How a pass is run] [Evidence]

6. **A cell is `pass` only when the observation and the artifact both exist.** A
   cell that ran, was read correctly and left nothing on disk is `not run` with a
   note. [How a pass is run]

7. **Evidence is what the execution produced, never a summary somebody wrote**:
   captured stdout and stderr with the exit code, wire bodies as they arrived,
   hash lines, listings, log lines, socket frames, journals. A coverage table is
   generated from a recorded sweep, never typed. [How a pass is run] [Evidence]

8. **One branch per minor for evidence, in the docs repository, and every host
   pushes into that one branch.** `evidence/<repo>-<version>`, cut once from a
   freshly pulled default branch there: a later operating system adds its
   boundary beside the first rather than opening a second pull request, and
   nothing else travels in it. [How a pass is run]

9. **A fix is verified by re-running the cell that found it**, whole and from its
   stated precondition, against a rebuilt and reinstalled product. A unit test is
   necessary and never sufficient.
   [A fix is verified by the cell that found it] [../README.md]

10. **Never edit a cell so it matches the behaviour you shipped.** If an
    assertion is genuinely wrong, say so in the cell's status and leave the
    assertion where the next reader can argue with it.
    [A fix is verified by the cell that found it]

11. **One failure is not a finding: reproduce before you diagnose, and reproduce
    through the same path the user used.** Behaviour that worked earlier with
    nothing changing it, and a failure you cannot reproduce on demand, are both
    evidence for a transient.

12. **Account for what the pass leaves running and on disk.** List and stop every
    process the pass started and show the ports free, and name the directories a
    group created in that group's cleanup column.
    [Account for what the pass leaves running]
    [Account for what the pass leaves on disk]

13. **One command at a time, and read its output and exit code before choosing
    the next.** A result from a command whose exit code you did not read is not a
    result. [One command at a time, and read its output before the next]

14. **Before you file a finding, suspect your own harness**, and do not stop one
    question early: a harness can create the condition while the product's answer
    to that condition is still wrong.
    [Before you file a finding, suspect your own harness]

15. **Finish the matrix: every cell carries a verdict or a named blocker**, and a
    blocked cell is owed only after the blocker itself was investigated.
    `Not-Needed` is a verdict with a reason, never a synonym for "did not run".
    [Finish the matrix] [Per-OS results] [../README.md]

16. **The oracle is never the product's own report.** The verdict comes from what
    the machine wrote down, and a claimed success with no confirming read-back is
    a fail; with neither journal nor transcript the result is `not verified`
    rather than a pass. [The approach] [../README.md]

17. **The runbook is complete before the first live cell, and the surface is
    enumerated rather than sampled.** Name the axes, multiply them, write the
    count, and give every cell an id, precondition, setup, action, expected
    observable, oracle, evidence boundary, cleanup and result slot. A check that
    needs something not built yet belongs to the minor that builds it.
    [Coverage] [../README.md]

18. **Evidence is filed while the pass runs, never assembled after it.** A bundle
    assembled once the answer was known is a bundle whose artifacts were chosen,
    and a group that captured nothing gets a note rather than a reconstruction.
    [Evidence] [../README.md]

19. **Credentials never enter Git or evidence.** Read only what a cell needs from
    the workspace `../.env`, never echo or copy a value anywhere, and run the
    secret check before every commit and before evidence is sealed.
    [Owner and environment requirements]

20. **Passes are independent only when each has its own port, database and
    daemon.** Two drivers sharing one daemon read each other's work and neither
    verdict means anything. [Repeatability] [../README.md]

**A pass is finished, not paused, and reporting is not a stopping point.** A
checkpoint or a progress summary does not end your turn: write it and keep
driving in the same turn. A pass ends when every cell carries a verdict or a
named blocker. Only a cell that cannot proceed without the owner, or a decision
only the owner can make, ends one early. Stopping to report looks like progress
and is the opposite, because the cells that were never run stay never run.

## How a pass is run, before anything else in this file

**These five rules come first because every one of them was learned by breaking
it. They hold on every supported operating system, for every agent that drives a
runbook, and they are not negotiable against a deadline or a token budget.**

**1. Whatever needs the owner runs first.** Before a single automated cell,
read the whole matrix, list every cell that cannot proceed without a human, and
run those cells at the start of the pass. A browser approval, a physical
handset, a hardware key, an elevation prompt, a paid account that must be
enabled: all of it is scheduled first, in one batch, with the owner told exactly
what to click and when. The owner is not a resource you discover you needed
after four hours of work. A pass that reaches its end and then asks for a
browser click has wasted the owner's day and produced a runbook that is still
`not run` where it matters most.

**Running them is the rule. Announcing them is not.** Naming the owner's cell in
an opening message and then starting part A satisfies nothing: the owner is
still waiting and the cell is still outstanding. If an owner-blocked cell needs
setup, that setup is the first work of the pass and nothing else is done until
the human observation is recorded. Before each command, ask **"is this the
owner's cell, or could the owner's cell run now instead?"** This paragraph
exists because `0.4.8`'s Windows pass announced the handset cell in its first
message and then ran five parts before reaching it.

**2. Do not stop the pass to report.** The pass runs to completion for the
operating system it is on. Findings, blocked cells, corrections and questions
are written into the runbook and the evidence as they happen, and they are
reported when the pass ends. The only thing that stops a pass is a cell that
physically cannot proceed without the owner, and rule 1 exists so that never
happens after the start. Reporting a blocker mid-pass, and waiting, converts one
run into many and leaves every later cell unexecuted.

**3. A bug you find is a bug you fix, here, now.** The purpose of an e2e is not
to catalogue defects. It is to establish that the product works on the target
operating system. So when a cell fails, you fix the code, you add a test that
fails without the fix and passes with it, you re-run the failing cell until it
passes, you commit and push to the PR branch, and only then do you carry on with
the rest of the matrix. **A finding recorded without a fix is a moved problem,
not a found one.** The fix ships on the PR branch as it is made; the branch is
the working surface, and holding a fix back to ask permission is the mistake.

**4. A fix invalidates the cells it touched, on every operating system that
already passed them.** A shared-behaviour fix means the earlier passes were
observing different code. Name the affected cells in the finding, mark them
`not run` again on the operating systems that had passed them, and say in the
per-OS matrix which fix invalidated them. The host that made the fix re-runs
them itself. The other hosts re-run them from the PR branch before merge. **No
operating system inherits a result from a build that no longer exists.** And a
rebuild is a new subject: re-run the identity cell and record the new binary
hashes **before any further cell**. A `0.4.9` pass filed a cell whose output
only a later commit could produce, under a host record naming the earlier head;
nothing tied any result to any build, and the whole pass was invalidated.

**5. The evidence is pushed, not left on the machine that produced it.** The
boundary directory is created before the first cell, each group files its output
at its own boundary, and **the whole boundary is committed on a branch and
opened as a pull request as part of the pass, not after somebody asks for it**.
A pass whose evidence sits in a temporary directory on the host that ran it is a
pass nobody can check: the numbers in the runbook have nothing behind them, the
next host cannot compare its own record against yours, and the directory is one
reboot from gone. Filing it is the last cell of every pass, and a report that
says the pass is complete while the artifacts are still local is wrong about
what complete means. This is written here because it happened: a full native
Linux pass was reported as done with its runbook results pushed and 51 evidence
files still in `/tmp`, and only the owner asking "evidence are pushed?" caught
it.

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

- **the API + both run WebSockets** - how the phone calls it, and the only way
  to know a mobile call behaves. Every socket the daemon serves is driven by a
  **real wire client**, its raw frames filed and their type counts recorded:
  the CLI watcher is one consumer of one socket and never stands in for the
  wire;
- **the CLI** (`vadgr run`, `vadgr runs get`) - the on-box path, with its own
  users and its own failure modes.

<Put the tested installation on `PATH`. Record `command -v vadgr` and prove its
target is the exact PR head. Invoke `vadgr ...` in the terminal. The installed
entry point is the installed binary; a product import, `cargo run` or a private
function is not an e2e invocation. A helper may prepare state and capture or parse evidence. It must not replace the
public CLI, drive the owner flow or choose the agent's actions.>

<The agent CLI invocation you actually used, so a reader can repeat it. Use
the CLI the machine has, and name it and its version beside the results; the
example is the `claude -p` form:>

```bash
claude --dangerously-skip-permissions --output-format stream-json --verbose -p \
  "<the goal-level task. Name a goal, never a call.>" \
  | tee /tmp/e2e-<version>.jsonl
```

## One command at a time, and read its output before the next

**Every product command is invoked on its own, and its output is read before the
next command is chosen.** This holds on every supported operating system and for
every agent that drives a runbook. A wrapper script that runs a whole group in
one shot is not an execution of that group, even when every command inside it is
the real public surface.

The failure it stops is specific. A batch prints one wall of output, so no line
can be attributed to the command that produced it. It reports one exit code, so
the exit codes of the commands inside it are never read, and **a result from a
command whose exit code you did not read is not a result**. A failure in the
middle is carried past by the lines printed after it, and the author writes down
the batch's outcome instead of each cell's. The batch also decides the order in
advance, which is exactly what an e2e must not do: what the previous command
returned is what tells you whether the next one is still the right one, and a
cell whose precondition was never observed is not a cell that ran.

So:

- Run one command. Read its output and its exit code. Record the cell. Then
  choose the next command.
- Never chain product commands with `&&`, `;` or a loop so that one invocation
  covers several cells.
- Never wrap a group in a driver script that logs in, runs, restarts and reads
  back without stopping.

A helper is still allowed exactly where it always was: it may build isolated
state **before** the group starts, and it may capture, sanitize or parse
evidence **after** a command has already run. It may not sequence the product
commands, and a file that does is a harness pretending to be an operator.

The exception is a single cell whose own definition is a loop or a matrix, such
as staging one weakened access control per isolated copy. There the repetition
is the cell, it is written that way in the table, and each iteration still
prints its own labelled result. If a reader cannot tell from the evidence which
command produced which line, the rule was broken whatever the file was called.

## Before you file a finding, suspect your own harness

**Most wrong answers in a pass come from the harness, not the product, and every
one of them looks exactly like a product failure.** These are the ones that have
actually happened here, each of which produced a confident false result until the
source was read. Check this list before writing a finding.

- **The tool's schema is not what you assumed.** A control tool called with the
  wrong field names errors instead of acting, and the cell reads as "the product
  did not do it". Read the tool's declared `properties` and `required`.
- **A policy or default silently changed the path.** The same tool called at
  `risk: low` is auto-allowed by the default policy and never parks, which reads
  as "it does not park". Only the input the cell actually describes exercises the
  cell.
- **You called a route that does not exist.** A `404` from a made-up path leaves
  the state untouched, so the next assertion tests the wrong state and passes or
  fails for the wrong reason. Grep the router before driving a verb.
- **You probed the right route on the wrong listener.** A surface served by its
  own listener on its own port returns `404` on the API port, which reads as
  "the route is missing".
- **You parsed a body you had already truncated.** Keep the full response for
  parsing and truncate only the recorded copy.
- **You counted one output stream.** An error belongs on `stderr`; counting only
  `stdout` reports correct refusals as producing nothing.
- **Your fixture branched on global state.** A provider stand-in that chooses its
  reply from a global call counter gets its parity shifted by every other run in
  the sweep and hands a later run the wrong arm. Decide from the conversation in
  front of it.
- **You polled slower than the window you were waiting for.** A screenshot
  completes in well under a second, so a one second poll walks straight past
  every moment in which a call is open. Match the poll to the event.
- **You left your own daemon running.** A leaked daemon holds its port, and the
  next run reads that as an environment condition. Stop every daemon you start,
  by pid, and check for strays before blaming the machine.

**A "no secret present" claim is verified against the raw artifact, never
against your own flag.** A check written as "does the redacted copy still
contain the secret" is tautologically false and will pass while a live
credential sits in the file beside it. Grep the file on disk.

## When a cell cannot be captured, ask whether that is the product's fault

An observable the runbook asks for and no platform can produce is usually a gap
in the product, not a limit of the harness. A shipped route served with no
tracing leaves no record of itself anywhere, so the row stays owed forever and
every platform records the same shrug. Fix the gap, then capture the row.

The repair for an observability gap is itself a place to be careful: adding a
default HTTP span to a route whose query carries a credential writes that
credential to the log. Record the identifiers, never the whole URI.

## Finish the matrix

**A pass ends when every cell has a verdict or a stated reason, not when the
first interesting result appears.** Partial results are the failure mode this
section exists to prevent: they read as progress, they are committed, and the
remaining cells quietly never run.

- A cell blocked by a host condition is owed only after the condition itself has
  been investigated. Two leaked daemons, a reserved port and a missing toolchain
  all looked like immovable environment facts and all three were removable.
- **"It needs a tool this host does not have" is a claim to check, not to
  report.** Look in this runbook's own `harness/` first: a cell that was called
  blocked on a missing QR decoder was closed minutes later by the decoder the
  suite already ships, which built and ran unchanged on the new OS. The suite
  carries its oracles so that every OS can run them.
- If a cell needs the owner, ask for that **first**, batch it, and keep working
  while you wait. Do not let one approval serialise the rest of the matrix.
- If a fix lands mid-pass, **re-run the cells it touches on every OS that
  already passed them**, because those rows were observed against the old
  behaviour.
- Report once, at the end, with everything. An audit delivered in instalments
  reads as an endless stream of problems and is really one incomplete sweep.

## Account for what the pass leaves running

**Cleanup columns cover a cell's state. They do not cover the processes the pass
started, and nothing else will.** A daemon is not evidence, so it is easy to
finish a matrix, commit it, and leave the fixtures alive.

An orphan does not stay harmless. It holds ports after the session that started
it is gone, and the next pass meets a port that is bound by nothing it can see,
which reads as a platform quirk rather than as yesterday's daemon. One pass here
left a daemon running for **twenty five hours**, its parent long dead, holding
the OAuth callback port `1455`; any provider login attempted in that window would
have failed to bind, and the cause would have looked like the host.

- **End a pass by listing every process it started and stopping it**, then
  showing the ports free. `Get-CimInstance Win32_Process`, `ps`, and the
  listening-socket table are the oracle; a `stop` command's own exit code is not,
  because it only speaks for the daemon it knew about.
- **Prefer the process table to the port table when diagnosing a busy port.** A
  port with no visible listener is more often an orphan of your own than a
  platform behaviour, and attributing it to the platform ends the investigation
  at exactly the wrong moment.
- Record the leftovers you found in the pass, even when you started them
  yourself. A daemon that survived a session is a fact about how the pass was
  run, and the next person inherits the habit, not the process.

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
the group. Stop when any ceiling is reached. Pixel or screenshot CUA requires
image input for the selected endpoint and image-bearing tool-result
continuation into the next model turn; record both in `required capabilities`.
A text-only model cannot close that visual group.>

## Prerequisites

<Everything a fresh machine needs, precisely enough to paste. Credentials,
env vars, isolated state, config, database and runs roots so no test reads or
writes the owner's normal installation, which port and which transport. Name
every feature toggle the group relies on. Before the first live submission,
read the effective settings through the product surface and assert them. A
fresh database that inherits the owner's config is not isolated.>

```bash
export E2E_ROOT="$(mktemp -d)"
export VADGR_DB="$E2E_ROOT/vadgr.db"
export VADGR_RUNS_DIR="$E2E_ROOT/runs"
export VADGR_STATE_HOME="$E2E_ROOT/state"
export VADGR_CONFIG_HOME="$E2E_ROOT/config"
export VADGR_PORT=8791
export VADGR_API_URL=http://127.0.0.1:8791
mkdir -p "$VADGR_RUNS_DIR" "$VADGR_STATE_HOME" "$VADGR_CONFIG_HOME"
cd "$E2E_ROOT"
<absolute-path-to-the-shipped-vadgr-daemon>

# In another terminal whose PATH resolves the tested installation:
command -v vadgr
vadgr health
curl -fsS "$VADGR_API_URL/api/health"
wscat -c "ws://127.0.0.1:8791/api/ws/runs/<run-id>"
wscat -c "ws://127.0.0.1:8791/api/runs/<run-id>/stream"
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


**The harness travels with this runbook.** Every helper the pass uses - the
recorder, the generator that turns its record into a table, a decoder, a stand-in
server - is committed at `E2E/<version>/harness/` with a README saying what each
one is and that none of them drives the product. **A helper that exists only in a
temporary directory on the machine that wrote it cannot be run anywhere else**,
so every other host produces a record nobody can compare, and comparison is the
point of a recorded sweep. Run each helper from its committed path before the
runbook is offered.

**Name what a host cannot do, not only what worked.** List the prerequisites the
pass actually hit, each saying **which cells it blocks** and what a host without
it records. A handoff assembled from the happy path leaves the next operating
system discovering a blocker four groups in.

<Provide paste-ready Linux/macOS shell and Windows PowerShell blocks. Use a free
loopback port per concurrent pass. A platform row with only "run the same test"
is incomplete.>

## Automated gate (necessary, never sufficient)

<The suites, green, with counts. Then one line on what they cannot tell you -
because on every runbook so far, the defects were in the seams the unit tests
stop at.>

- `cargo test` -> **N passed**
- `cargo clippy --all-targets -- -D warnings`, `cargo fmt --check` -> exit `0`

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

<**Generate these from the recorded session. Never type them.** The operator
invokes every public route and installed command. A recorder writes request,
status, error code and body to a JSON record. A post-run tool emits the tables
from that record. The recorder must not replace `vadgr`, drive the user flow or
import product code. A hand-written table drifts from the run it describes.>

<Before trusting the capture, verify that the installed `vadgr` command produced
the CLI result and that direct public calls produced the wire result. A
driver that invokes the product's own code rather than its installed command is
acceptance evidence, not e2e evidence.
Also reject an empty result or a CLI pointed at the wrong port. **Assert on
output, not only exit codes.**>

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

<Two tests every row passes before the pass starts. **The oracle can detect the
failure it names**: ask what it returns when the product is wrong, and if the
answer is "the same thing", it is not an oracle - a mint was once asserted
through a list the minted thing never appears in, and the cell could not fail.
**The boundary contains the artifact it names, never a sentence about it**: a
boundary that says hashes carries the hash lines themselves. "Unchanged: yes"
is the product's word taken for the state, which is exactly what an oracle
exists to distrust.>

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

**The rows are this runbook's own parts, and nothing else.** A row named for a
theme rather than a part cannot be read back to the cells that produced it, so a
reader cannot check it and a reviewer cannot audit it. `vadgr 0.4.7` shipped a
matrix whose rows were `credential matrix`, `live providers` and `full engine`,
none of which named a part or a cell, and it was unreadable for exactly that
reason. Add a row for the automated gate and one for the surface sweep if the
runbook has them, then `Overall`, and nothing else.

**Put the platform in the cell id wherever a case runs on several platforms**,
so the matrix row and the cells agree by construction: `BL` native Linux, `BM`
macOS, `BW` Windows native, `BQ` WSL, and `OS-L` / `OS-M` / `OS-W` / `OS-Q` for
an installed-product cell. Name those ids in the row's notes.

**`Overall` never inherits the automated gate.** CI builds an environment and
runs the unit suites. It drives no session, calls nothing over the wire and
reaches no glass, so a green CI row says the suites pass on that OS and nothing
about whether the product works there. `Overall` is the weakest of the parts
actually driven on that OS.

| part | Linux | macOS | Windows native | WSL | notes |
|---|---|---|---|---|---|
| automated gate: build, test, lint | | | | | |
| surface coverage | | | | | |
| Part <X> | | | | | |
| installed product on the host | | | | | name `OS-L`, `OS-M`, `OS-W`, `OS-Q` |
| **Overall** | | | | | |

<Justify every `Not-Needed` in prose. "No socket, pipe, path or registry
/process branching and no per-OS deps, so the other OSes cannot behave
differently" is a reason. Silence is not, and neither is "it should be fine".

Anything touching the filesystem, spawning a process, resolving a credential
store, binding a port or drawing native UI is **owed**, not excused.>

## What this runbook cannot prove

<The honest limits, so nobody reads a green table as more than it is. Every
runbook has some; a runbook claiming none has not been thought about.>

- <...>
