# <version> - <what this minor made true>: e2e runbook

> **<repository> <version> implementation:**
> `<branch name> at <exact head commit before the first host passes>`.
> **<repository> <version> evidence PR:**
> `<resolved private evidence PR URL>`.
>
> Resolve the branch and head before the first development cell. Resolve the
> evidence link before any captured artifact leaves its host and before the first
> formal candidate cell. The evidence link names the one private evidence branch for this minor. Every host
> adds its boundary to that pull request; it does not open another evidence pull
> request. After the first real target OS passes and branch checks are green,
> replace the branch/head line with the implementation PR URL before handing the
> branch to another host. Do not open a draft or reservation PR to fill this
> line: publication itself requires that first live pass.

> **Read this whole file before you run anything, and read
> [`README.md`](README.md) beside it.** Not the rules that look relevant to the
> cell in front of you: the whole file. Every rule in it was written because a
> pass broke it, and a pass that starts at the first cell meets them one at a
> time, each at the cost of the thing it was protecting.
>
> **This instruction exists because a rule that was already written, already
> indexed and already in front of the driver was broken by three separate
> passes**: evidence for `vadgr 0.4.7`, `0.4.8` and `0.4.9` was pushed straight
> to the docs default branch instead of the minor's evidence branch, once per
> release, by a host that had the rule on its screen. Reading the document is
> the cheapest of every remedy available, and it is the one that was skipped.

<One sentence: what a reader is being convinced of. Not what changed - what is
now demonstrably true that was not before.>

> **Status: <not started | development qualification on \<OS\>, \<date\> | partially run on \<OS\>, \<date\> | run on \<OS\>, \<date\>>.**
> Automated gate <green/red> (engine N, api N), **and the pull request's own
> checks finished and read**. <Which parts pass, which are open.> **N findings**, listed below. Nothing is marked pass that was not
> executed and read back.
> The header, the coverage counters and the per-OS table are re-read against
> the cell marks before the runbook is offered: a file that says `not started`
> over cells that say `pass` is wrong twice, and a reader cannot tell which
> half to believe. Count the rows, then read the counters against them.

<Copy this file to `E2E/<version>/e2e.md` and fill it in. Delete these angle
bracket notes as you go; a leftover placeholder is the tell that a runbook was
written and never run. The cross-cutting rules are in
[`../README.md`](../README.md) and are not repeated here.>

## Development qualification before the candidate

<Keep this section when the implementation can run before final signing,
publishing or dependency release. Delete only statements that do not apply.>

Development qualification starts as soon as an exact implementation commit can
run safely in isolated state. It does not wait for signing identities, a signed
tag, immutable release assets, a published dependency or a final evidence PR.
Use the latest available released dependency when it can exercise the behavior,
and record its exact version. A dependency source commit intended for the next
release may also be tested from a separate clean worktree when the runbook names
that provenance. Never touch an existing dirty dependency worktree.

Mark these results `development`, not `pass`. Signing, notarization, package
identity, immutable artifact, clean-host and final bundled-version assertions
wait only when their required subject does not exist. Run every unaffected
action and oracle now. A missing release-only input does not block console,
daemon, API, accessibility, provider, device or currently available computer-use
behavior. Development findings are real defects: fix them, add the failing test,
rebuild and rerun the affected development cell.

### Qualification lanes

<Fill both ledgers before the first live cell. Put each assertion in the lane
required by its actual oracle, not by the cell number that happens to contain
it. A mixed cell appears in both rows with its assertion slices named.>

| lane | assertions in this minor | execution rule | completion meaning |
|---|---|---|---|
| unsigned development qualification | <cell ids and exact non-signing assertion slices> | run immediately on every available host; signing is not a blocker | development evidence only; never a signed-candidate pass |
| signing-only acceptance | <cell ids and exact publisher/chain/timestamp/notarization/designated-requirement/trust/update assertion slices> | run when the immutable signed subject exists | required for release acceptance |

Do not park an entire mixed cell behind signing. Terms decline, ordinary
install/launch, console and daemon behavior, accessibility, phone transports,
isolated repair/uninstall/data deletion, offline operation and cleanup remain
development-runnable unless their individual oracle consumes a signed subject.
Keep the signed assertion in the second ledger and preserve its original
expected result.

### Package production before merge

Functional qualification consumes the exact release-equivalent **unsigned**
installation vehicle registered by the approved design and distribution
matrix. Producing that vehicle is implementation work, not post-merge signing
work. If the vehicle, its credential-free producer, its reviewed non-secret
package inputs, or its pinned private payload is missing, record an
implementation finding and fix or create the packaging on the existing
implementation branch. Run the affected source gates, build the vehicle,
record its inventory and digest, and continue the functional cells.

Do not wait for a protected post-merge workflow artifact merely because that
workflow is the final producer. Do not substitute a source checkout, loose
binary, system runtime, package from an earlier commit, another operating
system's vehicle, or a different package format. A missing production signing,
notarization, timestamping, attestation or catalog identity blocks only the
assertions whose oracle consumes that identity. Protected CD after merge must
sign, attest and hold the exact final product shape; it must not be the first
time ordinary packaging is exercised.

When the missing input is genuinely owner-supplied, finish every independent
repair first, then name the exact non-secret file or approval and the precise
resume action. Never ask the owner for a signing credential during the
pre-merge lane.

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
   cell that cannot proceed without a human, prove that automation cannot do
   the required step, and run those cells before any unattended one. The agent
   drives every other action. **Running them is the rule; announcing them is
   not.**
   [How a pass is run] [../README.md]

   For a phone QR cell, the agent uses ADB/accessibility to launch the mobile
   app, select the intended machine and transport, reach the live scanner, and
   handle every automatable permission or dialog. The owner's row contains only
   the physical camera aim and its exact visible stop condition. Never ask the
   owner to open the app, navigate, choose a transport, type a code, inspect the
   result, or report an oracle the agent can read. A pass uses that physical
   scan once. Every later pairing, including revoke and re-pair, is driven by
   the agent through ADB and the `vadgr://pair` operating-system link. A cell
   that would need any other owner action on the handset is `not run` with
   that reason.

   A VM-hosted phone is checked through the host ADB server before it is called
   unavailable. Detect the current hypervisor and network mode first; never
   inherit a previous host label or assume its gateway. Stop the guest-local
   server before setting a remote socket. For verified VirtualBox NAT, derive
   the guest default gateway and set `ADB_SERVER_SOCKET=tcp:<gateway>:5037`. Use
   that same socket for every ADB command. The runbook gives the temporary host
   server start and restore commands, requires an authorized `device` state,
   forbids network-service mutation, and redacts the device serial.

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
   nothing else travels in it. **The default branch is never the target**, on
   any host, for any reason, and a pass that cannot find the branch asks for it
   rather than pushing past it. Broken once per release for three releases
   running, always by the same host and always with the rule on screen, so it is
   now a check rather than a sentence. [How a pass is run]

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

21. **The agent drives the native console through accessibility.** Discover and
    operate semantic controls through the platform tree, confirm each transition
    with a fresh structured read, capture only the exact application client area
    without requiring focus, inspect it against the approved mockup, and verify
    each effect with an independent machine oracle. [Native console driving]

    On Linux, use the latest released Vadgr CUA MCP server in an isolated test
    environment, not the subject's bundled payload. This Linux-only rule
    overrides older direct-helper instructions. Use real MCP `ui_tree`,
    `ui_find` and `ui_act` calls with fresh references and structured readback.
    Record the driver identity separately from the product identity. No provider
    API key is needed for these local tool calls. Do not import product modules.

    Use `PrintWindow(PW_CLIENTONLY)` under a per-monitor-aware DPI context on
    Windows. Use `SCScreenshotManager` with an
    `SCContentFilter(desktopIndependentWindow:)` on macOS. On native Linux, use
    one XDG Desktop Portal ScreenCast WINDOW source and its PipeWire stream on
    Wayland, or the target window ID and XComposite window pixmap on X11. Prove
    once per host that capture works while another application has focus. A
    focused capture, desktop capture, monitor capture or crop is not a
    substitute. An unavailable exact unfocused capture leaves the visual
    assertion owed. [Native console driving]

22. **A native console has no silent dead controls.** Invoke every enabled
    control through accessibility. Each future control is disabled and visibly
    names the exact registered minor that enables it. A current-state limitation
    shows its truthful reason instead. [Native console driving]

23. **Production signing starts only after merge.** An open implementation PR
    uses an exact release-equivalent unsigned artifact for functional E2E.
    Every applicable functional assertion gates merge. Protected CD then signs
    a held candidate from the exact merged default-branch commit. Only trust and
    signature assertions wait for that candidate and gate release. [Unsigned
    functional qualification and post-merge trust qualification]

24. **A supported VM is valid native functional coverage when the guest runs
    the product directly.** Record the hypervisor, guest OS, virtual hardware,
    architecture, desktop and display protocol. Label it virtualized native
    coverage, not bare-metal coverage. Leave hardware-specific behavior and
    unavailable architectures or sessions `not run` with the exact reason. A
    VM does not turn WSL, a container or a host-mounted checkout into native
    coverage.

25. **Missing unsigned packaging is an implementation defect, not a signing
    blocker.** Repair or create the credential-free producer and required
    reviewed package inputs on the implementation branch, build the registered
    vehicle, and continue the host pass. Do not wait for protected CD or replace
    the registered vehicle with a more convenient format. [Package production
    before merge]

26. **Desktop visual inspection is a separate, mandatory oracle.** Open and
    inspect the actual application-only captures of every installer and console
    state in the visual checklist. A correct accessibility tree, backend result,
    screenshot file, or owner report does not establish a visual pass. Raw
    Markdown in a formatted terms view is a rendering finding, not a cosmetic
    exemption. [Desktop visual acceptance]

**A pass is finished, not paused, and reporting is not a stopping point.** A
checkpoint or a progress summary does not end your turn: write it and keep
driving in the same turn. A pass ends when every cell carries a verdict or a
named blocker. Only a cell that cannot proceed without the owner, or a decision
only the owner can make, ends one early. Stopping to report looks like progress
and is the opposite, because the cells that were never run stay never run.
A status question, or any other question the owner asks while work runs, is
not a stop instruction: answer it briefly and keep driving in the same turn.
Only an explicit pause or stop instruction, or a genuine owner decision, ends a
turn before the work is done.

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

**An owner cell contains only an unavoidable human boundary.** First prove that
no safe automation or accessibility interface can perform the step. Prepare the
exact application and surrounding state. Then give one instruction which names
the physical or protected action, the printed control or object involved, and
the visible result that returns control to the driver. Camera scans, device
unlocks, private credential entry, elevation, and protected operating-system
prompts can qualify. Routine clicks, key entry, navigation, captures,
application launches, and screen reports do not qualify when the interface can
perform or inspect them. On a phone, the owner's only action in a pass is one
QR scan with the scanner the agent already opened. Every later pairing,
including revoke and re-pair, is driven through ADB and the `vadgr://pair`
link, and a cell that would need any other owner action on the handset is
`not run` with that reason.

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
what complete means. This is written here because it happened twice, the
second time in the runbook that already carried this rule. A full native Linux
pass was reported as done with its runbook results pushed and 51 evidence files
still in `/tmp`. Then a full native Windows pass, on a runbook whose first
screen is this paragraph, closed 85 cells and reported them complete with every
artifact still under `%TEMP%`, and the owner caught it with the same question:
"evidence are pushed?"

**So it is checked now, not remembered.** `check_e2e.py` fails a runbook whose
per-OS table claims a pass on an operating system with no evidence boundary
filed for it. Prose stopped neither pass, and the two other rules this project
had to convert into scripts, the branch point and the attribution trailer, were
converted for exactly this reason. **A reading typed into a status column is not
evidence. The artifact is, and the artifact lives in the docs repository.**

**One branch per minor, and every operating system pushes to it.** The evidence
for a release is one change: `evidence/<repo>-<version>`, cut once from a freshly
pulled default branch, carrying one boundary directory per host. The second host
to finish does not open a second pull request; it pulls that branch, adds its own
boundary beside the first, and pushes. The pass is not complete for the family
until every host that ran has filed into it.

**Nothing else travels in that branch.** Not a script, not a rule, not another
release's evidence. A reviewer opening an evidence pull request is reading
evidence, and a diff that also moves a checker or a second minor's artifacts
cannot be read as either. If you find yourself adding a non-evidence file, the
branch point was wrong: cut a new one for that subject.

This is written because the alternative was tried. `0.4.9` produced one branch
for the WSL boundary and a second for the Windows boundary, so one release's
evidence sat in two pull requests that had to be reviewed against each other,
and a third subject and a fourth release's artifacts drifted into one of them
until the gate refused it. **One release, one branch, one review.**

**And a cell is `pass` only when both halves exist.** The verdict is the
observation **and** the artifact behind it. A cell that ran, was read correctly,
and left nothing on disk is not `pass`; it is `not run` with a note, because
there is nothing a reviewer or the next host can check. Write the status from
the artifact, file the artifact, and if you cannot file it, say so in the status
rather than claiming the cell.

**What counts as evidence, stated because the wrong answer is the tempting
one.** Evidence is what the execution produced:

- the command's own **stdout and stderr, captured to a file**, and its **exit
  code**;
- the **wire body** a request returned, saved as it arrived, not paraphrased;
- the **file listing, the hash lines, the process table row, the log lines** the
  cell's oracle names, copied verbatim;
- for a socket, the **captured frames**; for a run, the **journal**.

**Evidence is not a summary you wrote.** A sentence saying the daemon answered
`200`, a table you typed from the terminal, a status column reading "all fields
match", a count you remember: none of these are evidence, however true they are.
They are a **reading of** evidence, and a reading with nothing under it is worth
exactly as much as a reading of something that never happened. The reader cannot
tell the two apart, which is the whole problem.

The test is simple and it is worth applying to every file you file: **could
somebody who does not trust you re-derive your status line from this artifact
alone?** If the answer needs your prose to bridge a gap, the artifact is
incomplete and the gap is where a mistake lives. A `sha256` line either side of
an operation passes that test. "The file was unchanged" does not.

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

**A cell asks a paired repository only for what it has released.** This product
is one of several that call each other: the phone is a separate repository on
its own version, and so is the computer-use runtime. A cell that asks the phone
to do something the shipped app cannot do is a cell specified against a surface
nobody built, and it fails for a reason that has nothing to do with the release
under test.

So before writing any cell that touches a paired repository, **read that
repository, not its README**: its released tag and the source behind the screen
or the tool you are about to ask for. Then **name the version the cell depends
on**, in the runbook, in the paired-surfaces section every runbook carries:

```markdown
## Paired surfaces this pass depends on

| repository | released version | what this pass relies on |
|---|---|---|
| vadgr-mobile | 0.4.1 | the app reads machines and runs and consumes the run stream |
| vadgr-computer-use | 0.7.3 | the screenshot and shell tools, over stdio |
```

The rule runs in both directions: this runbook does not ask another repo's
client for a surface it has not shipped, and it does not assume a daemon route
that has not shipped either. **A cell whose surface arrives in a later release
is written into that release's runbook, and its absence here is stated rather
than silent.**

It is written down because a `0.4.9` cell told the tester to start a run from
the phone. Starting a run from the phone is the mobile app's `0.5.0`; the
shipped app is a reader. The owner found it holding the handset.

**A cell driven by a person is written for that person.** Where a part is held
in someone's hands rather than run in a terminal, the operator drives the
machine and the tester does only what the cell says, in the order it says it.
So the cell names **every action on the device and every prerequisite on it**:
the network or VPN the handset must join, the app state it must start from, the
taps in order, and what to read back. A tester cannot see the daemon, the
transport or the state, and cannot infer a step that was left out.

The prerequisites are the half that gets forgotten, because they are invisible
from the machine: a `0.4.9` pass handed the tester a QR without saying to turn
the tailnet on first, and the handset simply could not reach the address in the
code. **A step the operator performs by habit is a step the cell has to state.**

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

## A fix is verified by the cell that found it, not by the test you wrote for it

**A fix exists because a cell failed. That cell is the verdict, and it is not
closed until it has been run again, against the rebuilt product, and its status
rewritten from what the re-run showed.** A unit test that fails without the fix
is necessary and it is never sufficient: it proves the function you changed does
what you now think, on the machine you are typing on. It says nothing about
whether the thing the cell was watching works, which is the only question the
cell was ever asking.

The order is fixed, and every step is owed:

1. The cell fails. Record what it printed, before you touch anything.
2. Fix the code, with a test that fails without the fix and passes with it.
3. **Rebuild and reinstall the product the cells drive.** A cell re-run against
   the old binary is a cell that did not run. On Windows the running daemon
   locks the file, so this means stopping it first.
4. **Run the cell again, whole, from its stated precondition.** Not a smaller
   version of it, not the one command you think was the interesting part.
5. Rewrite the cell's status from the re-run, and say in it that it failed first
   and why. A cell that passes with no history reads as a cell that was always
   fine, and the next reader loses the defect.
6. **Re-run the cells the fix invalidated on every operating system that had
   passed them**, per rule 4 at the top of this file.

**Never edit a cell so that it matches the behaviour you shipped.** If a cell's
assertion is genuinely wrong, say so in its status, with the evidence, and leave
the assertion where the next reader can argue with it. Weakening the oracle to
turn a red cell green destroys the only record that the product ever behaved
differently, and it is indistinguishable from the product having been fixed.

Both halves were broken in `0.4.9`'s Windows pass, in the same hour. A per-OS
matrix row was written as passing before the cell behind it had been re-run at
all, and a fix to the installer was called done on the strength of its function
being checked in isolation, while the cell that found it, a from-nothing install
followed by an update, was never driven again. Neither is a lie about the code.
Both are a claim about the product that no run supports.

## Account for what the pass leaves on disk

**A directory a pass creates is cleaned up by the group that needed it, at that
group's boundary.** Not at the end of the pass, which may not arrive, and not by
the next person, who will not know it was ours. This is the same rule as the one
below for processes, applied to the other thing a pass leaves behind, and it
fails more quietly: a stray directory costs nothing today and silently changes
the answer to a cell that runs weeks later.

That is not hypothetical. In `vadgr 0.4.9`, `J1` requires the platform state
root absent or empty. It was **blocked** on a machine where the product had
never been installed, because an earlier pass had left two empty directories
under `%LOCALAPPDATA%\vadgr`, created as a side effect of resolving a path. Zero
files, zero bytes, and enough to stop the cell. The pass that made them ran to a
clean verdict and never knew.

- **Name the directories a group creates in that group's `Cleanup` column**, the
  same way a cell names the daemon it must stop. A group whose cleanup column
  says `none` is asserting it created nothing, and that assertion is checked.
- **Isolated roots are removed when the last group that reads them is done**,
  not left "in case". Evidence that must outlive the pass is filed under the
  runbook's evidence directory, which is the one place a later reader expects to
  find things.
- **A platform location is never a scratch directory.** State roots, config
  directories and anything under a user profile are the product's, and a pass
  that writes there restores exactly what it found, listing the location before
  and after.
- **Check for your own leavings before you call a cell blocked by the
  environment.** A precondition that a directory is absent is usually failing
  because an earlier run of this same runbook created it, and the fix is to
  clean up rather than to record a blocker.

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

## Native console driving

<Delete this section only when the minor has no native graphical surface. Name
the exact accessibility backend and the command or tool used to inspect it. Use
the standard host-native application-only capture path named in doctrine and
prove that it works while another application has focus. A focused capture,
desktop capture, monitor capture or crop is not a substitute. If exact unfocused
capture is unavailable, leave the visual assertion owed. The driver opens every
capture and compares the complete view with the approved mockup. Screenshots
confirm rendering but never locate controls or drive the structured tier.
If the owner explicitly authorizes a temporary Linux focused-region exception,
record that ruling and its affected visual assertions in the current runbook.
Focus the exact owned test window through accessibility and independently verify
fresh display-space crop geometry. Never interpret untrusted Wayland or
window-relative accessibility bounds as global screen coordinates. If supported
window maximization supplies that geometry, record and restore its prior state.
Verify structured focus immediately before and after the public MCP
`screenshot_region` call. Exclude occlusion, other applications and secrets.
Inspect the returned image before retaining it. Reject changed focus, uncertain
bounds or unsafe pixels. Label qualifying output `focused region`, never
`unfocused window`. This exception can satisfy only its authorized visual
inspection slice; the exact unfocused capture assertion remains unproven.
Keep the missing capability assigned to its approved future minor. Do not
generalize this exception to other platforms or use pixels for ordinary input.>

<Inventory every console control before the first live cell. An enabled control
must work in this minor. A future control must be disabled and show the exact
registered minor that enables it. A control unavailable because of current
machine state shows that reason instead. Do not assign a future version to a
temporary state.>

| view | accessible name | role and action | state in this minor | enabling minor or state reason | independent oracle | cell |
|---|---|---|---|---|---|---|
| <view> | <printed label> | <role and supported action> | <enabled / disabled future / disabled by state> | <current / X.Y.Z / reason> | <daemon, package, process, file or OS read-back> | <id> |

<The driver invokes every enabled row through the accessibility interface. It
confirms every disabled future row is inaccessible to activation and visibly
shows its version label. An enabled no-op, an inaccessible enabled control, or
an unlabeled future control is a finding.>

### Native desktop cold-start checklist

Keep this checklist in every desktop minor. Read the docs engineering section
"Native desktop cold-start procedure" before the first GUI cell. Fill in exact
helper commands and supported interfaces; a pointer alone is not a procedure.

For Linux, record the verified released CUA installation, doctor and MCP server
launch commands before the first call. Inspect its advertised schemas over the
real MCP connection. Do not assume checkout or bundled-payload tools are the
released tools. Windows UIA and macOS Accessibility keep their existing drivers.
Direct Linux accessibility helpers are diagnostic only, not the primary driver.
Register the verified installed entry point with
`codex mcp add <name> -- <absolute-installed-entry> --transport stdio`.
Reload the client tool catalog only when needed to expose the new server.
Inspect startup side effects before launch: isolate driver-owned writes and
preserve existing browser-registration manifests and other owner configuration.
Keep the real desktop bus available. Driver write isolation is not evidence
that the tested application ran natively inside a container. The subject still
runs through its registered native vehicle. Ordinary setup is the agent's job;
ask the owner only for a genuinely protected permission. Successful MCP
initialization or a reachable accessibility bus is not full application coverage.

Isolate the tested application's child HOME as well as its XDG state, data,
configuration and cache roots. Bundled native-host registration can use HOME
directly. Preserve the real desktop session bus, runtime directory and display;
do not replace the external MCP driver's environment. Before a bundled task,
verify the installed daemon's actual environment and private-runtime identity,
and confirm that owner browser registrations remain unchanged.

Measure installation readiness from the spawned daemon's process identity, not
from the earlier installer-window launch. A failed or timed-out installation
must leave no late daemon, dangling command registration or selected deleted
generation. Observe the failed state again after its startup interval, preserve
the failed attempt and verify rollback independently. A healthy API without an
admitted bundled runtime is not successful package qualification. Owner-disabled
computer use is distinct from missing runtime admission.

Do not treat a successful stop command as proof of process exit. Before rollback
or removal deletes an installed generation, verify that its exact daemon and
bundled child processes have exited. A reused PID, changed process identity or
unrelated port listener must not be stopped. A stop failure must preserve the
generation and report the failure instead of continuing destructive cleanup.

#### Session-tool preflight

Prove three separate facts: the server starts, the client discovers its tools,
and the current agent session can call them. A configured server, a tool count
in `/mcp`, or a successful standalone Python MCP probe proves neither the last
fact nor a GUI cell. Use an actual exposed `get_platform_info` tool call before
ordinary accessibility actions. Inspect any authorized visual smoke result
returned by the exposed screenshot tool; full-desktop output is not app-only
capture evidence. Do not replace a missing agent tool with a shell wrapper.

For Codex, record the CLI and background-server versions and whether Remote
Control is active. A terminal restart can leave the shared server running.
Check the effective server configuration, tool allow/deny lists and current
thread inventory. An `unknown` status alone does not identify the failure.
When discovery succeeds but the session lacks the tools, use the client's
documented MCP reload. The app-server protocol provides
`config/mcpServer/reload`, which reloads configuration and queues refreshes for
loaded threads. Verify the request against the installed version's schema;
version 0.159.3 accepts `{"id":1,"method":"config/mcpServer/reload","params":null}`
after its normal initialized connection handshake. Send it through the existing
local control connection, not a newly exposed network listener. Recheck the
agent's callable tools and perform an actual tool call after the refresh.
Do not repeatedly restart the VM, reinstall CUA or change networking to repair
session discovery. Coordinate any necessary shared-server restart so it cannot
interrupt unrelated work. Reference: the official Codex app-server and MCP
documentation; recheck it for the installed version.

Installing repaired wheel bytes does not replace code already loaded by an
MCP server. An unchanged configuration reload can retain that process. After an
authorized driver repair, bind a nonsecret source identity in the server-specific
configuration and request the supported reload. Verify a new process and the
exact installed artifact, reacquire the exposed tools, and make an actual tool
call before rerunning the cell. A reload acknowledgement alone proves neither
process replacement nor tool readiness. Keep the development driver identity
separate from the released baseline and the subject's bundled payload.

Accessibility remains the primary Linux control tier. Reproduce CUA failures
through the exact released public tool before filing an issue. Check for an
existing issue and include the release, host class, safe minimal steps,
expected and actual results, and independent oracle. Exclude owner data,
private paths, credentials and unsafe captures. Record the issue reference
with the affected assertion. A client reload problem is not a CUA defect.
Filing the issue does not complete the work. Fix confirmed defects, add a
regression that fails without the fix, rebuild and rerun the affected public
MCP actions and assertions. Identify a repaired development driver separately
from the released baseline; never relabel its bytes as the released artifact.
Keep driver-fix qualification separate from qualification of the subject's
bundled CUA payload. Record an exact external or protected-owner boundary only
when it genuinely prevents completion.

#### Close a CUA driver repair through its release

A development repair or an open CUA PR does not close the dependency finding.
Qualify the appropriate patch release and required version-plan realignment.
Before assigning a version, fetch the latest published tag and default branch,
compare the version register, and inspect all unreleased default-branch changes
that the release would include. A merged feature is not a released dependency.
Never publish unqualified unrelated work to obtain one fix. If those changes
conflict with a maintenance release, record the exact scope and obtain the
owner's route decision before renumbering or proceeding.
Merge any version-plan realignment as one consistent change before tagging.
Preserve required reviews and branch protection without administrative bypass.

Complete the repair's negative regression, required live cells and source/CI
gates. Obtain the applicable owner merge and release approvals, then follow the
CUA protected candidate and publication gates without bypasses. This procedure
does not authorize unrelated merges or releases. After publication, install the
verified released artifact in the isolated driver environment. Record its tag,
source and artifact digest, reload into a verified new MCP process, and confirm
the current session can call its tools. Rerun every affected consuming Vadgr
assertion from its stated precondition and preserve the earlier failures.
Only that released-driver rerun closes the finding. Development-driver proof
and the subject's bundled-CUA qualification remain separate. Continue independent
cells while a specific owner approval or producer prerequisite remains owed.

#### Continue the cold-start checklist

- Probe the current host/session and virtualization; do not carry a historical
  hypervisor label across a resumed pass. Record artifact and process identities, plus
  original accessibility and screen-reader settings, including unset values.
- Keep a passive launch observer separate from product lifecycle control.
  When a user service hosts an installer observer and its surviving console or
  daemon, use `RemainAfterExit=yes` if the observer can finish first. Otherwise,
  service completion can kill the remaining control group. Keep normal explicit
  cleanup protection; do not disable it globally. Verify the actual unit settings
  before launch, and do not stop the unit until public product shutdown has been
  observed. Record direct-child exit and inherited-pipe completion separately.
  After a reboot, reacquire process identities and check retained state before
  resuming. Never infer successful product shutdown from observer termination.
- Prove actual screen-reader readiness before its state matrix. A speech-server
  initialization message is not an active accessibility event loop or application
  speech. Bound startup and shutdown, record the exact reader PID/start identity,
  and retain only allowlisted nonsecret utterances. Focus each tested control and
  wait for its actual utterance before dismissing it; a quick focus-and-close
  sequence can remove the control before speech is produced.
  On Linux, first record Orca, libatspi and toolkit versions. If bounded probes
  reproduce synchronous desktop-discovery starvation before the event loop,
  inspect those exact upstream sources and compare a controlled cache-enabled
  startup. Where supported, an isolated `orca-customizations.py` may call
  `Atspi.get_desktop(0).set_cache_mask(Atspi.Cache.DEFAULT)` before normal Orca
  startup. Use the installed reader's supported customization loader, isolated
  XDG configuration and the real desktop bus. Record the customization digest;
  do not modify system packages, owner configuration, application discovery or
  speech generation. Preserve the failing default and control probes. This is
  a conditional environment workaround, not a product fix or an upstream-release
  claim. Require actual application speech and terminal reader exit separately;
  a successful observer unit or collected unit's default properties prove neither.
  For readers with this supported loader, put the customization at
  `$XDG_DATA_HOME/orca/orca-customizations.py` inside the isolated test root.
  Import `gi`, call `gi.require_version('Atspi', '2.0')`, import `Atspi` from
  `gi.repository`, then make the cache call above. Verify the installed loader's
  path before launch; a file merely present elsewhere does not enable it.
  Use an external process-group or user-service deadline as well as the
  observer's deadline. A synchronous discovery stall can prevent an in-process
  timer from running. Record the bounded shutdown and the exact reader's
  absence, including after a failed probe. Restore only the assistive settings
  changed by the pass, and never replace the owner's reader configuration.
- Prove bounded accessible-window readiness and exact control discovery. Use a
  fresh process-scoped tree, supported native action, fresh readback and an
  independent machine oracle for each step. Action dispatch is not success.
  On Linux, obtain these through released MCP `ui_tree`, `ui_find` and `ui_act`;
  reacquire references after changes rather than reusing stale nodes.
  Inspect the actual schemas: an application-name filter is not a PID filter.
  Match `ui_windows` discovery to the independently known launch PID and start
  identity, then use the exact application filter and refuse ambiguity. Retain
  only bounded, reviewed nonsecret fields; do not invent safe-filter arguments
  or save an unfiltered owner-window list or accessibility tree.
  An action can remove its own control, such as Save closing an editor. Preserve
  a post-action `element_gone` reply, reacquire fresh semantic state and check the
  independent machine oracle before deciding whether the mutation occurred.
  Do not replay a potentially completed action or rewrite its reply as success.
  If a transient layout change invalidates a reference before dispatch,
  reacquire the exact named control rather than reuse its old reference.
- Verify native focus after asynchronous in-place actions, not only before
  dispatch. While the same control remains on the same page, loading,
  completion and error notices must not silently replace its accessible
  identity or lose keyboard focus. Pair the settled tree with the saved-value
  oracle and actual reader output. A successful save alone does not pass this
  check. Also verify that a late completion never takes focus back after the
  user has moved to another control or page. Dialog closure has its own
  deliberate focus destination; do not require the removed control to survive.
- Exercise focus across every dialog family, not only the first confirmation.
  Opening a dialog must establish a meaningful safe focus destination once;
  later frames must not take focus from the user's selected control. Destructive
  dialogs must not initially focus their destructive action. Test nested
  transitions, cancellation, Escape, outside dismissal and successful or failed
  completion. Preserve the original opener across a nested dialog chain. Return
  to that enabled surviving control, or a deliberate same-view fallback when
  it no longer exists. A late result must not reopen a dismissed dialog or take
  focus after navigation. Verify settled native focus, actual reader output and
  unchanged state separately. A frame-only focus state is not a control-focus
  pass, and a cancelled operation is not evidence for its unrun success path.
- When another operation is pending, an unavailable submission must stay
  disabled and state its reason inside the dialog. Verify that the draft
  remains intact and cancellation remains available. Conditional waiting text
  must not change surviving control identities or lose focus. After completion,
  verify the submission's actual state and independent outcome. A dialog that
  closes without dispatching its requested operation fails. Exercise this
  through an ordinary installed operation where available; do not manufacture
  timing or infer installed coverage from a source regression.
- Prove enabled/disabled semantics and native text replacement on isolated
  ordinary fields before settings, credentials or typed purge. On Linux,
  `EditableText.SetTextContents` must actually work; an editable flag or click
  action is not sufficient. Do not replace this proof with injected keys,
  clipboard, backend writes or owner typing.
- Prove the required unfocused application-only capture. On Wayland use the
  portal WINDOW source and scoped PipeWire stream. A missing row action or
  refused Selection is a recorded capability failure, not automatically an
  owner-only permission prompt. Cancel the owned chooser after a bounded probe.
  Linux visual checks use the release's public MCP capture tools. A release
  exposing only full-screen screenshot/crop does not satisfy this exact
  app-only oracle. Leave it owed if unavailable; never invent window capture or
  count a desktop crop as equivalent. Helper probes remain diagnostic records.
- Name helper dependencies, safe tree filtering, exact new output paths and
  cleanup commands. Never retain private window titles or secret-bearing trees.
- Record unavailable assertions separately, continue independent cells, and
  restore the exact original settings and owned processes after testing. After
  a reboot, rediscover readiness and identities before resuming.

#### Conditional Wayland chooser and unfocused capture probe

This section describes a diagnostic capability probe. It does not override the
released MCP driver requirement or turn direct-helper captures into MCP proof.

The portal contract does not prescribe a chooser layout or focus order. Verify
the installed portal backend, desktop and toolkit versions and their matching
source before using a backend-specific selection path. The agent chooses each
action from a fresh native tree; a helper must not implement this journey.
An absent accessible portal application before its first chooser is created is
normal preflight, not permission denial. After creation, require the exact
owned application and chooser frame before any action.

If a bounded ordinary selection probe fails, retain it. A missing row action
or refused Selection does not establish an owner-only protected prompt. Where
the verified backend supports the following sequence, use two separately
identified, bounded ScreenCast requests, each restricted to one WINDOW:

1. Open request A and leave its chooser open. Launch a new test-owned target
   window, then open request B. Distinguish both chooser instances from fresh
   process and window identities; never select by a shared title alone.
2. Inspect B. Continue only if its first candidate is the exact target window,
   is `FOCUSED` and `SENSITIVE`, and is not defunct. Never infer the target from
   ordering alone. If these predicates fail, cancel the owned requests.
3. Invoke the chooser root's observed `default.activate` action only when
   **Share**, the current default control, is insensitive and the matching
   backend source establishes that this fallback activates the exact focused,
   sensitive, non-defunct target row. Reacquire B and require the target to be
   the sole `SELECTED` window and **Share** to be sensitive.
4. Select B's exact **Share** control with role `button`, `SENSITIVE` and
   non-defunct. GTK may omit `ENABLED`; do not require both flags. Invoke its
   observed action. A same-named label is not a button.
   Cancel A through its exact **Cancel** button, scoped to A, not B.
5. Launch a fresh, harmless test-owned cover window. A `window.present` request
   alone does not prove Wayland focus. Independently record the target inactive
   and the cover active before image acquisition, and recheck afterward.
6. Require one returned WINDOW stream and reject any exposed non-WINDOW source
   type. Read only that request's scoped PipeWire stream. Inspect the image,
   then close both owned requests and stop only test-owned cover processes.
   Retain the full stream image and its dimensions, including any black padding;
   do not crop it into an apparent success or substitute a desktop image.

Stop on ambiguity, unexpected focus, selection or stream identity. Keep every
failed probe; do not retry indefinitely, bypass the chooser, capture a monitor
or desktop, crop, or present a focused image as unfocused. This is a conditional
capability probe, not a guarantee for every GNOME or Wayland version. The
[ScreenCast interface](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html)
defines source types and stream/session scope, not this chooser sequence.

### Desktop visual acceptance

Keep this gate for every native desktop release. Before the first GUI cell,
enumerate its installer, console, dialog and lifecycle states. Map each state
to its functional cell, a dedicated Part V cell and approved mockup. Do not
replace the dedicated visual cells with a general accessibility row. Capture the exact installed
artifact through the required native application-only path, then open and
inspect each image at its intended reading size. Record the artifact digest,
host/session, window size, display scale, theme, capture digest and observation.
Repeat affected visual states after every rendering fix and rebuilt artifact.

Inspect these properties explicitly:

- Terms and bundled legal views render headings, paragraphs, emphasis and lists
  as readable document content. Markdown markers such as `###` and `**` must not
  leak into a formatted view. Intentional literal source or code views are
  separate, clearly labeled surfaces. Rendering must not change the approved
  legal source bytes, terms version, acceptance hash or substantive text.
- Text remains readable at the default and minimum supported window sizes and
  supported display scales. Check wrapping, scrolling through long content,
  clipping, contrast, alignment, spacing and reachability of controls. Check
  both themes when the application supports them.
- The visible unchecked, checked, enabled, disabled, focused, loading, empty,
  populated, failure, destructive-confirmation and success states agree with
  the fresh accessibility tree and independent machine oracle. A disabled
  control must look disabled and reject activation. Inspect installer terms
  before acceptance, not only the final success screen.
- No placeholder, unintended markup, missing glyph, overlapping text, hidden
  action, unlabeled future control or private implementation detail appears.
  Use isolated non-secret data. Never capture a pairing code, token, private
  endpoint or credential merely to fill the visual ledger.

| view and state | functional cell | exact artifact and capture digests | window, scale and theme | visual observation | result |
|---|---|---|---|---|---|
| <each installer, console and dialog state> | <existing cell id> | <digests or exact capture boundary> | <actual settings> | <what the agent inspected> | <pass / fail / not run with reason> |

A successful capture command alone is not an inspection. A tree or API result
cannot close a rendering assertion. If the required exact capture cannot be
made, preserve the failed native probe and leave that visual assertion owed.
Continue independent functional assertions, but never promote their success to
a visual pass or call the GUI qualification complete. Do not ask the owner to
inspect the screen in place of the agent.

Verify how the installed toolkit exposes size, scale and system appearance
before attempting alternate configurations. A configured minimum size is not
an observed minimum-size pass. Do not invent unsupported accessibility methods
or substitute X11 or GTK environment overrides for Wayland compositor scaling.
Record the actual appearance preference: no preference is not explicit light.
An isolated session bus can change appearance discovery, so record that scope.
Use only authorized, reversible native settings changes and restore their exact
original values. Leave only the unsupported assertion owed, with its proved
interface boundary, rather than blocking independent work.

For failure states, inspect the visible message as well as preservation of
installed state. The message must identify failure and a safe recovery action;
an operation label alone does not explain failure. Never expose raw error
chains containing private URLs, paths or credentials to make the message useful.

Keep reusable procedures here. Put dated attempts, real host identifiers,
private paths, process identities and captures only in the approved evidence
boundary after its privacy checks, not in this template. Use placeholders in
examples and never copy secret-bearing trees, pairing material or account data.

## Owner and environment requirements

<Complete this table before the first live cell. Tell the owner what is needed
before the affected group starts. Never print or persist a secret while checking
availability. A missing item blocks the already-written cells; it does not
remove them or reduce the matrix.>

<Host networking is never e2e state. Do not change the host firewall, DNS,
routing, proxy, VPN or network service. Model a network failure in isolated
test state. A host network change is never an e2e cell.>

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

<Use live internet access on the execution date to read current official model
and pricing pages, then intersect those results with the authenticated catalog.
Routine cost targets today are the Claude Sonnet, GPT Luna at medium reasoning
and Gemini Flash families; GPT Terra is the next OpenAI lane only when Luna
lacks a required capability. They are examples, not frozen ids or a permanent
allowlist. A newly launched cheaper capable model replaces them. Never infer
price from catalog order or model naming. Fable, Sol, Opus and equivalent
frontier tiers are prohibited for setup, navigation, screenshots, smoke tasks
and ordinary provider-neutral cells. A frontier row is valid only when it names
the captured lower-cost capability failure from the same cell, the prewritten
escalation condition that fired and a separate hard cost ceiling. A persisted
expensive default must be changed before routine billed work.>

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
  Use one explicit build root whose resolved path is below this checkout's
  ignored `target/` directory. The source-workspace protection regression
  identifies its checkout from the test executable's actual ancestors.
  An external build root does not satisfy that precondition. Do not remove or
  weaken the regression to accommodate a misplaced build cache.
- `cargo clippy --all-targets -- -D warnings`, `cargo fmt --check` -> exit `0`

**The gate is not green until the pull request's checks have finished.** The
suites above ran on one machine, the one the pass was driven on. The pull
request runs them on **every operating system in the matrix**, and those are the
machines nobody looked at. **A pass is not closed and a pull request is not
offered for review while a check is still running.** Waiting costs minutes; a
release announced green over a check still running is a claim about machines
nobody read.

So the last step of a pass is to watch the checks to completion, record their
result here beside the local ones, and only then call the pass closed. A red
check is a finding like any other: it is fixed and the cells it invalidates are
run again, or it is written down with its reason. This is here because a `0.4.9`
pull request was offered as finished while its Windows job was still running,
and that job went red.

## Unsigned functional qualification and post-merge trust qualification

<Use this section when a minor adds or changes a signed application, installer
or package. Delete it when the minor has no signing surface.>

Local development and the ordinary host pass use an exact release-equivalent
unsigned artifact. Label it development-only. Record its source commit,
inventory and hashes. Do not copy a production signing key, token or certificate
to a workstation. The open PR and its artifacts must not consume production
signing credentials.

The pre-merge pass proves every functional assertion which does not require a
platform trust identity. Installation, update, repair, rollback, pairing,
accessibility, state preservation and failure behavior normally belong here.
Complete these assertions on every required host before merge. An unsigned pass
proves no publisher identity, trust chain, timestamp, notarization, designated
requirement, attestation, adoption or operating-system reputation behavior.

Merge authorizes candidate production, not release. Protected CD creates one
held, non-public candidate from the exact merged default-branch commit. Record
the source, workflow, target, inventory, hashes, provenance and signing identity.
The signing job accepts product source only from that protected branch.

Run only the assertions that require the held signed subject before a final tag
or public release. These include platform signature verification, trust chains,
timestamps, notarization, designated requirements, attestations, adoption and
exact-byte promotion. Repeat a functional assertion only when signing or final
packaging changed the behavior it proves. A failure blocks release and is fixed
through a new implementation PR. The next merged commit produces a new
candidate and invalidates affected earlier verdicts.

Post-merge trust checks are CD and release validation. They are not a second
full host E2E gate.

Release promotes the exact signed bytes that passed. CD does not rebuild or
re-sign them after qualification. Before publication, compare the held
artifact's SHA-256, provenance and platform signature with the recorded
candidate. After publication, download the public assets and repeat that
identity comparison. Neither comparison is a first signing E2E pass. Any
changed byte, source tree or signature stops release and creates a new candidate
that must run the affected cells.

| stage | artifact | required identity | gate |
|---|---|---|---|
| open implementation PR | release-equivalent unsigned development build | source commit, inventory and SHA-256 | one real OS plus ordinary source gates opens the PR; every required functional OS assertion gates merge |
| post-merge protected candidate | signed, held and not public | exact merged default-branch commit, source-tree hash, workflow run, provenance, inventory, SHA-256 and platform signature | signature and trust assertions gate tag and release; repeat functional work only when final packaging changed it |
| release promotion | the same qualified bytes | candidate inventory, SHA-256, provenance and signatures match exactly | identity check before publication and after download; never a first signing pass |

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

| # | Precondition and setup | Goal or action | Owner action | Expected observable and oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|---|
| X1 | <state and setup> | <goal-level task or action> | <none, or one unavoidable physical/protected action with the prepared state, exact instruction and visible completion result> | <observable result and independent machine oracle> | <files/records captured now> | <restore/remove> | <pass / fail -> Fn / blocked: reason / not run> |

**Measured.** <The actual output, pasted. Ids, counts, tokens, exit codes -
whatever a reader would need to disbelieve you with. A table of passes and no
evidence is a claim.>

```
<paste>
```

<One line on why this evidence is the right evidence. On this product it is
usually: the journal is the proof and the status is not, because a run ends
`completed` on the legacy path too.>

### Complete uninstall outcomes

For uninstall cells, observe the complete user-visible outcome, not only file removal.
Successful removal must close the product console and stop its owned runtime.
Verify process exit and package, launch-entry and listener absence independently.
Cancellation must preserve the usable installation. Pending removal must not
announce completion or close early. A failed removal must keep the console open
with a specific error and available recovery action. Never count a stale console
showing a missing-daemon error as successful uninstall UX.

## Part B: installed bundled computer use

Unsigned qualification proves the complete installed product before release.
Include real runs, provider connections, bundled CUA, mobile pairing, transports
and lifecycle operations on every supported OS and applicable shipped surface.
Signing must not be the step that enables these features for the first time.
The release pipeline adds signatures and distribution trust metadata, then
verifies final identity, integrity and promotion. Those checks do not replace
the unsigned functional pass or erase an outstanding functional finding.

Keep B01 whenever Vadgr ships a bundled computer-use runtime. Expand its result
by every supported host, architecture and applicable desktop session.
Do not infer one platform's pass from another platform or a hosted producer.
Inventory, private-Python startup, tools/list and truthful unavailability are
separate assertions. None proves a real task through the installed product.
The external testing MCP never substitutes for the subject's bundled runtime.

Run the functional task before merge on Linux, macOS, Windows and WSL.
If the unsigned package cannot execute it, record and fix that implementation
finding. Missing development admission is not a signing-only blocker.
Provide an explicit, integrity-checked, non-publishable development execution path.
Never fabricate adoption metadata, disable production verification or substitute
another runtime. Keep final signing, attestation and adoption assertions separate.
Each supported host requires its own installed-artifact task result.
Do not call bundled computer use qualified until the task passes.

Prepare an isolated nonsecret fixture window with a fresh visible test marker.
Submit this goal through the installed Vadgr CLI or API:
"Use computer use to capture only the prepared test window and report its visible test marker."
Freeze the exact command, artifact, image-capable model and hard budget first.
Follow the billed-model and capture rules in this runbook. No phone is required.
Require a successful bundled tool call, its returned image, a model continuation
reading the marker, and terminal success in the same run journal.
Inspect the returned image and compare the marker with the independent fixture.
Bind the executing child and private interpreter to the installed payload hashes.
Check that no system Python, checkout, external MCP or runtime override was used.
Keep private paths and secret-bearing outputs out of retained evidence.

| cell | platform | precondition and setup | action | independent oracle | evidence boundary | cleanup | result |
|---|---|---|---|---|---|---|---|
| B01 | <each supported host, architecture and desktop> | <exact installed artifact, pinned bundled runtime, approved authorization, safe fixture, image-capable provider and budget> | run the bounded screenshot-and-marker task through installed Vadgr | journal tool call, image and continuation; fixture match; installed process, interpreter and payload identities | private exact-source/artifact/run evidence and inspected safe output | remove only task-owned run, fixture and processes after filing | not run: populate exact runtime and provider prerequisites before execution |

## Part V: native lists and dialogs visual qualification

Keep these nine cells in every minor with native graphical surfaces. Replace
the surface examples with the complete shipped inventory; do not sample only
the first model, provider or dialog. Delete this part only when the product has
no native GUI, and state that reason. These are pre-merge functional cells;
production signatures do not block their unsigned qualification. WSL is
`Not-Needed` for this part because its product is CLI-only. It does not inherit
the Windows GUI result. Expand supported architectures and desktop sessions
inside each host ledger; a result on one variant never qualifies another.

### Visual matrix and independent oracles

Before execution, list every shipped surface in these three groups:

1. Provider cards, the provider chooser, authentication-method choices and every
   model/default-model list or chooser.
2. Every other list, including devices, grants, skills, MCP servers and any
   shipped legal, diagnostics or settings list.
3. Every dialog and installer frame, including edit, connection, cancellation,
   destructive confirmation, terms, progress, error and success views.

For every surface, enumerate each reachable empty, populated, loading, error,
selected, unselected, focused and disabled state. Add the shipped confirmation,
success and cancellation states. Record an exact reason when a state does not
exist for that surface. A shipped state that cannot be reached with available
prerequisites stays `not run` or `blocked`; do not remove it from the matrix.
Use isolated nonsecret data, including long labels and multiline text where
the public product permits them. For provider/model lists, use actual catalog
entries; do not invent a model or rewrite the catalog to manufacture a pass.
Include enough real entries to exercise scrolling and inspect the first,
middle and last entries, selected state and action row.

Cross that inventory with default/full-window and minimum supported sizes,
both supported themes and every supported scale required by the platform
design. Record actual native dimensions, scale and appearance, not requested
values. Name every combination in a ledger before execution and count them.
Configured minimums, offscreen tests and screenshots at another scale are not
native visual results. If the interface cannot safely set a supported variant,
record the exact capability probe and leave that variant owed. Never modify
host networking or owner data to manufacture loading, failure or empty states.

Drive ordinary controls through native accessibility: Windows UIA, macOS AX,
and the released external CUA MCP accessibility tier on Linux. Reacquire state
after every action. Use the native application-only capture policy and the
current runbook's explicit Linux exception, if one exists, without expanding
it. Open and inspect each actual image at its intended reading size against
the approved mockup for that surface. A saved image, accessible tree, source
review, unit test or backend success alone never establishes a visual pass.

Inspect hierarchy, grouping, row and section spacing, padding, alignment,
contrast, text wrapping and control reachability. Compare measured geometry
and contrast with the approved design's values where specified. Record visible
deviations; do not invent a new aesthetic threshold. Check long names, selected
and disabled contrast, clipped or overlapping text, horizontal overflow,
scroll containment, stable dialog/footer placement and reachable actions at
both ends of long content. Installer frames must retain their approved brand,
progress and content hierarchy. An accessible but visually hidden action fails.

**Contrast is checked on the installed rendering, in both light and dark.**
For each shipped control, inspect normal, hover, keyboard-focus, pressed,
selected and disabled states wherever implemented. Record the actual painted
text/icon foreground and adjacent control/background, including focus and
selection indicators. Check these against the approved design and applicable
accessibility contrast floors. Theme constants, accessibility names and source
regressions cannot establish the colors a user actually sees. Black text on a
dark button, or another visibly unreadable foreground/background combination,
is a **FAIL** and blocks the affected visual verdict even when activation works.

Use the approved disabled-state styling and readable explanatory copy; disabled
controls must remain distinguishable from enabled controls. Do not invent a
mandatory contrast ratio for inactive controls where the applicable standard
exempts them. Mark a state not applicable only when the product does not
implement it. A supported state that the available interface did not exercise
remains owed with the exact boundary, not implicitly passed.

Measure the final painted foreground and adjacent background after opacity and
compositing. Source regressions must use the renderer's actual blend operation;
a different color-space calculation can falsely pass unreadable installed text.
Check the required boundaries of empty enabled text fields and checkboxes, plus
visible focus indicators, separately from text. Do not impose a control-boundary
ratio on decorative card borders or a selection fill whose state is conveyed
by readable text. Inspect all shipped semantic status colors on their actual
surfaces, not only the first failed button.

Retain the failing installed image with its artifact identity. A source repair
or green widget test does not change that result. Rebuild, verify the new
installed bytes, and inspect the affected state/theme combinations again before
recording a repaired visual pass. Keep the failed and repaired subjects separate.


Corroborate the displayed rows, selection and enabled states with the public
API, CLI, package receipt or filesystem. After selection/save, verify the
independent persisted value; after cancellation, verify it is unchanged.
Do not submit a billed task merely to inspect a model choice. Any required
provider validation still obeys the model-selection and cost ceilings above.
Never capture credentials, account identifiers, pairing material or private
endpoints. An unsafe required image remains an explicit evidence boundary,
not a reason to retain it or pretend a partial image proves the whole view.

Record each image digest, exact artifact and source, mockup revision, host,
surface/state, actual size/scale/theme, inspected observations and independent
oracle. Preserve failed images and failed actions, then fix, rebuild and rerun
every affected combination. A shared picker, dialog or theme change requires
affected native Windows, macOS and Linux reruns. Historical O2 or functional
results do not automatically pass these cells. Restore selected models, test
data, window state, appearance, scale and assistive settings after each group.

| cell | platform | precondition and setup | action and expected visual result | independent oracle | evidence and cleanup | result |
|---|---|---|---|---|---|---|
| VW01 | native Windows, supported architectures | exact installed artifact; safe provider/catalog state and complete group 1 matrix | UIA drives provider/model lists; inspect actual app-only images against the approved grouping, spacing, contrast and overflow rules | provider/catalog API plus persisted default; cancellation preserves it | private per-combination records; restore provider/default state | not run: this minor's Windows provider/model matrix must execute |
| VM01 | macOS, supported architectures | exact installed artifact; safe provider/catalog state and complete group 1 matrix | AX drives provider/model lists; inspect actual app-only images against the approved grouping, spacing, contrast and overflow rules | provider/catalog API plus persisted default; cancellation preserves it | private per-combination records; restore provider/default state | not run: this minor's macOS provider/model matrix must execute |
| VL01 | native Linux, supported architectures and sessions | exact installed artifact; external MCP driver; safe provider/catalog state and complete group 1 matrix | MCP accessibility drives provider/model lists; inspect authorized images against the approved grouping, spacing, contrast and overflow rules | provider/catalog API plus persisted default; cancellation preserves it | private per-combination records; restore provider/default state | not run: this minor's Linux provider/model matrix must execute |
| VW02 | native Windows, supported architectures | exact artifact and complete group 2 matrix; isolate list data | UIA drives every other shipped list, including long and scrollable content; inspect actual images at every required variant | corresponding public API, CLI or owned-file inventory | private per-combination records; remove only test entries and restore settings | not run: this minor's Windows other-list matrix must execute |
| VM02 | macOS, supported architectures | exact artifact and complete group 2 matrix; isolate list data | AX drives every other shipped list, including long and scrollable content; inspect actual images at every required variant | corresponding public API, CLI or owned-file inventory | private per-combination records; remove only test entries and restore settings | not run: this minor's macOS other-list matrix must execute |
| VL02 | native Linux, supported architectures and sessions | exact artifact, external MCP driver and complete group 2 matrix; isolate list data | MCP accessibility drives every other shipped list, including long and scrollable content; inspect authorized images at every required variant | corresponding public API, CLI or owned-file inventory | private per-combination records; remove only test entries and restore settings | not run: this minor's Linux other-list matrix must execute |
| VW03 | native Windows, supported architectures | exact artifact and complete group 3 matrix; isolated lifecycle state | UIA opens every dialog and installer frame; inspect hierarchy, wrapping, focus, disabled states, footer reachability and cancellation | independent state before/after; package/process oracle for lifecycle frames | private per-combination records; restore preserved state and owned settings | not run: this minor's Windows dialog/frame matrix must execute |
| VM03 | macOS, supported architectures | exact artifact and complete group 3 matrix; isolated lifecycle state | AX opens every dialog and installer frame; inspect hierarchy, wrapping, focus, disabled states, footer reachability and cancellation | independent state before/after; package/process oracle for lifecycle frames | private per-combination records; restore preserved state and owned settings | not run: this minor's macOS dialog/frame matrix must execute |
| VL03 | native Linux, supported architectures and sessions | exact artifact, external MCP driver and complete group 3 matrix; isolated lifecycle state | MCP accessibility opens every dialog and installer frame; inspect hierarchy, wrapping, focus, disabled states, footer reachability and cancellation | independent state before/after; package/process oracle for lifecycle frames | private per-combination records; restore preserved state and owned settings | not run: this minor's Linux dialog/frame matrix must execute |

Each row is independently runnable from its named setup. Only an unavoidable
protected permission or physical device step requires the owner; prepare it
first. Continue independent surfaces while that exact assertion is pending.
Include Part V in Coverage, the per-OS table and the completion ledger. Count
nine cells plus the minor's other cells; separately report the expanded matrix
combinations actually observed. A partial combination matrix is not a cell pass.

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
| Part B | not run: exact installed bundled task owed | not run: exact installed bundled task owed | not run: exact installed bundled task owed | not run: exact installed bundled task owed | name B01 and the exact runtime, artifact, authorization and provider prerequisites; no external-driver substitution |
| Part V | not run: native list/dialog matrix owed | not run: native list/dialog matrix owed | not run: native list/dialog matrix owed | Not-Needed: CLI-only product | name VL01-VL03, VM01-VM03 and VW01-VW03; retain unavailable variant reasons |
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
