# vadgr - the machine daemon

A daemon per machine: the native agent loop, the MCP host, gates and policy,
the API the phone talks to, persistence, plus `src/cli/` - the on-box owner
surface.
v2 has no desktop frontend - `0.4.2` deleted it, and a guardrail test fails the
suite if it comes back. The clients are this CLI and the phone.

**This file is loaded automatically. The rules live in the docs repo and are not
copied here** - a second copy drifts, and a drifted rule is worse than none.
What follows is the handful of things that must not be looked up, plus where to
look for everything else.

## Before you touch anything

```bash
gh repo clone MONTBRAIN/vadgr-docs        # if it is not already beside this repo
```

Read, in this order, and stop as soon as your question is answered:

1. **`vadgr-docs/PLANS.md`** - the phases, the iterations, the pairing table,
   and the decision register. **Most "which way should this go" questions are
   already ruled there. A decision marked `Ruled` is an answer, not an option.**
2. **`vadgr-docs/general/CONTRACT.md`** - the API and CLI surface, endpoint by
   endpoint, each tagged with the minor that delivers it.
3. **`vadgr-docs/general/ARCHITECTURE.md`** and the minor's design doc under
   `vadgr-docs/design/phase-<N>-<name>/vadgr/<version>/`.
4. **Only then ask the owner** - and say which of the three you checked.

`vadgr-docs/AGENTS.md` and `vadgr-docs/general/ENGINEERING.md` are the full
conventions. **Read them before your first change in a session.** They are not
auto-loaded, which is exactly why this file names them.

## Four things that must never be looked up

**1. This repo is public. The private docs are never named in it.** Not
`CONTRACT.md`, `PLANS.md`, `ARCHITECTURE.md`, `ENGINEERING.md`, `MOBILE_DESIGN.md`,
no `D-xx` decision id, no `vadgr-docs/` path - in code, comments, docstrings,
test names, the CHANGELOG, or a PR body. **State the substance instead**: "the
published API reference", "the published frame vocabulary", "the engineering
standard". Sweep before every push:

```bash
grep -rn "\bCONTRACT\.md\|\bPLANS\.md\|\bARCHITECTURE\.md\|\bENGINEERING\.md\|\bMOBILE_DESIGN\.md\|vadgr-docs\|\bD-[0-9]" \
  --include=*.rs --include=*.md --include=*.toml . | grep -v "AGENTS.md\|CLAUDE.md"
```

**The exception, stated so it is not guessed at: this file and `AGENTS.md` name
the private docs on purpose** - they are the entry point, and a pointer that
cannot name what it points at is useless. The ban is on everything a stranger
reads as the product: code, comments, docstrings, test names, the CHANGELOG and
PR bodies. Those cite the substance, never the document.

**2. No AI attribution, anywhere, and it is checked.** No `Co-Authored-By`, no
"generated with", no credit to a tool - in commits, PR bodies, comments or
generated files. `scripts/check_no_ai_attribution.py` runs in CI over the same
range and event the credential gate uses, because this rule was a sentence for a
year and **five commits still reached a release branch crediting a model**.

**A credit is not a mention.** Naming a model is a fact this product states
constantly: a catalog entry, a run's model id, the CLI that drove an e2e, "the
model returned a 429". All legal. What fails is credit for the work: a trailer
naming a model, a generated-with line, a claim that a tool wrote it.

**3. Design comes before code.** No minor is implemented until its build spec
exists and every minor in its iteration has one:

```bash
python3 ../docs/scripts/check_iteration.py <phase> <iteration>
```

(The script resolves its own paths, so only the path to the docs checkout
matters: `../docs/` on the working machine, `../vadgr-docs/` where it was cloned
under its own name.) Exit `0` or do not start. This exists because the rule was
written down and broken twice in an hour.

**4. PR bodies carry code, tests, user-visible changes and caveats.** No
methodology narration, no SOLID tables, no design-doc citations.

## Cross-platform PR handoff

**One real operating-system pass opens the PR; every required operating system
still gates merge.** This applies to machine-side changes in `vadgr` and
`vadgr-computer-use`. Complete and pass the runbook on at least one real target
OS, then open the PR as cross-platform incomplete. Record the passed OS and
leave every untested OS as `not run` or `blocked` with its exact requirement.

The PR branch is the handoff. Agents on the other operating systems fetch that
branch, run their native cells, and push results and required fixes back to the
same branch. If a later platform fix changes shared behavior, rerun affected
cells on every earlier passing OS. The owner can review the evolving diff, but
the PR is not merge-ready until every required OS is `pass` or has an approved
`Not-Needed` reason, every finding is resolved, and the final branch checks pass.
Opening the PR is a collaboration gate. It is never cross-platform acceptance.

## Current research before design

**An iteration starts from dated evidence, not remembered facts.** Run `date`
when the iteration starts and record that date in every design doc. Before a
design decision, use web search and upstream source search for every fact that
can change: providers, models, authentication, API endpoints, SDKs and
libraries, platform behavior, lifecycle or deprecation status, limits and
pricing. Prefer current primary official sources. When documentation does not
settle open-source behavior, inspect the current upstream source and record its
exact commit. For account-scoped provider facts, also inspect the authenticated
catalog or run a bounded live probe.

The design's `Research basis` records the URLs, dates, exact versions, model ids
or commits, and the capability evidence that informed the design. Recheck
changing facts on the implementation and e2e execution dates. If current
evidence is unavailable, stop; memory and stale examples are not design input.

## Billed E2E model selection

**No billed model call starts from a remembered or flagship default.** On the
execution date, inspect the provider's official model and pricing pages plus the
authenticated account catalog. Choose the least expensive available model that
supports the exact endpoint, function or tool calling, content types, context,
and multi-turn behavior the cell exercises. Record the model id, capability
evidence, input/output price, expected worst-case usage, hard iteration/token
and cost ceilings, and the condition for any escalation before the call.

Pixel or screenshot CUA requires image input and image-bearing tool-result
continuation on the selected endpoint. Verify both against current official
model documentation and the authenticated catalog. A text-only model cannot
close a visual cell, regardless of its lower price.

An automatic product-selected model is tested once because it is user-visible
behavior. Repeated provider-neutral work uses an explicit cost-effective model.
Test another model only when it represents a distinct protocol or capability
class, a written cell requires it, or the cheaper model failed for a recorded
capability reason. Stop at the ceiling; never upgrade silently or use a
frontier model merely because it is available.

## The practices every repo in this family follows

**This section is identical in every code repo, and identical in this repo's
`CLAUDE.md` and `AGENTS.md`.** An agent loads one or the other depending on the
tool it runs under, and it must not get a different standard depending on which.
The long form of every rule here is `vadgr-docs/general/ENGINEERING.md`; these
are the ones that cost the most when missed.

**Ask in this order, and asking is the last resort**: `PLANS.md` including the
decision register, then `CONTRACT.md`, then `ARCHITECTURE.md` and the minor's
design doc - **then** the owner, saying which you checked and what each did not
answer. **A decision marked `Ruled` is an answer, not an option.**

**Do not bring a problem without a decision.** Anything found is either fixed,
or written into `PLANS.md` under the minor that owns it, with the reason. A
defect reported with no disposition moves the work rather than doing it.

**A migration is not a literal translation.** Read the old implementation for
shipped behavior and live consumers. Read the plan, contract, architecture and
release design for the target. The target documents win when they disagree.
Port target behavior. Keep only the smallest adapter required by a named
released consumer, with its removal release recorded. Do not port dead entities,
retired integrations, deprecated subprocess paths, external client
configuration, duplicate sources of truth, known defects or misleading status.
Fix a defect when its code is rewritten and add a regression test. The
comparison sweep detects differences; it does not define the target.

**"A named released consumer" means one you can point at.** A shipped client, a
released artifact, an installation that exists. Not a hypothetical user, not "in
case someone", not the machine you are typing on when you are the only
installation. **If you cannot name it, the adapter is not compatibility; it is
the translation you were told not to write**, and it costs a deprecation path, a
test in both directions and a removal release nobody needed.

Caught in `vadgr 0.4.8`'s first draft: the design proposed reading the old
`FORGE_*` environment names beside the new `VADGR_*` ones, with a deprecation
warning and removal at `0.5.0`. There is exactly one installation, it is the
owner's, and it sits on the same machine as the new state root the Rust daemon
already writes to. The adapter served nobody. **The rename, told
plainly, was the target**, and the directory moves once at the cutover that owns
the paths rather than twice.

**Design comes before code.** No minor is implemented until its build spec
exists and every minor in its iteration has one. Exit `0` or do not start:

```bash
python3 ../vadgr-docs/scripts/check_iteration.py <phase> <iteration>
```

Exit `0` is necessary and never sufficient: it checks that specs exist and are
structurally complete, and it cannot review one.

**When the implementation must diverge from the approved design, that is an
owner decision, and the design doc is realigned after.** Implementation reveals
what the design could not: a binding that will not load, a coordinate the
session withholds, a toolkit that hides its tree until asked. Do not build the
divergence silently and move on. Surface it to the owner with the decision and
its fundamentals, the way every owner decision is surfaced, and let the owner
judge it. If the owner approves, update the design doc to match what was built,
so the design stays the source of truth and the next reader is not misled by a
spec describing what was replaced. A design left describing the code that no
longer exists is a defect, the same as a stale comment. This holds in every repo
in this family.

**CI is not an e2e pass.** The automated gate builds an environment and runs the
unit suites. It drives no session, calls nothing over the wire and reaches no
glass, so a green CI row on an OS says the suites pass there and **nothing at
all** about whether the product works there. An OS whose only evidence is CI is
marked `not run`, never `pass`, and a runbook's `overall` row never inherits a
gate result: it is the weakest of the parts actually driven on that OS. This
shipped once and was caught in review, with two platforms marked `pass (CI)`
while their own live rows read `not run`. **A suite is not a session.**

**The runbook is complete before the first live cell runs.** Every surface
branch and enum-shaped edge case is an independently executable cell with a
stable id, precondition, setup, action or goal, expected observable, machine
oracle, evidence boundary, cleanup and result slot. A prose list, a count with
no matching cells or a "remaining matrix" row is unfinished. List every
required credential, paid account, OS, device, application, permission,
destructive action and owner decision up front, map each to its cells, and
inform the owner before the affected group runs. Missing setup blocks written
cells; it never deletes or collapses them.

**The owner's cells are the first cells executed, and announcing them is not
executing them.** A pass identifies every cell that cannot proceed without a
human and **runs those first**, before any unattended cell. Naming the
owner-blocked cell in an opening message and then starting part A satisfies
nothing: the owner is still waiting, and the cell is still outstanding at the
end. If such a cell needs setup, that setup is the first work of the pass.
Before each command, ask **"is this the owner's cell, or could the owner's cell
run now instead?"** Leaving it for later is the pass treating the owner's time
as the cheap resource, which is backwards: the machine can wait and the person
cannot. Written twice now, because the weaker form failed twice, the second time
in the same message that had just quoted the rule.

**A runbook another operating system can run, and a harness it can run with.**
The remote-host handoff is written before another OS is asked for anything, and
it is complete enough that a session with no context executes the pass from it
alone. **Every helper lives at `E2E/<version>/harness/`**, committed beside the
runbook with a README saying what each one is and that none of them drives the
product: a helper sitting in a temporary directory on the machine that wrote it
cannot be run anywhere else, so every other host produces a record nobody can
compare. Run each from its committed path before offering the runbook, and list
the prerequisites the pass actually hit, **each naming the cells it blocks**. A
handoff assembled from the happy path leaves the next OS finding a blocker four
groups in, which is what it exists to prevent.

**Credentials never enter Git or evidence.** Local e2e reads only the required
variables from the workspace `../.env`, without echoing values or placing them
in command arguments, logs, screenshots, transcripts, process listings, PR
titles, PR bodies, review comments, documentation or evidence. The file stays
untracked and owner-only: mode `0600` on Unix and an owner-only DACL on
Windows. Before every commit and before evidence
is sealed, run `python3 scripts/check_no_secrets.py --env-file ../.env`. If any
credential reaches Git or GitHub, stop, rotate it first, purge it from history,
and rerun the scan. Redaction alone does not make an exposed credential valid.

**The e2e is run before the PR is published, and the owner reviews the results,
not a plan.** Whoever builds the change runs the e2e the feature needs - a browser
change against real sites, a desktop or structured change against real
applications, never a mock - and ships the results in the PR. There is no
approve-the-runbook-before-it-runs step: the owner reviews the results and asks for
changes if they do not convince. A PR that claims a feature works with its e2e left
unrun is incomplete.

**Two conditions gate opening it, and neither has an exception:**

1. **The e2e has passed on at least one real target OS**, with its results in the
   PR. Not written, not drafted: run, with the artifacts. This binds any change
   that reaches shipped behaviour. A pure documentation change has no e2e to run,
   and the PR says that rather than leaving the reader to guess.
2. **The branch checks are green on the head being pushed.** A failing check the
   author already saw locally and pushed anyway is worse than a surprise: it says
   the gate is decoration.

**Draft is not an exemption.** A draft PR is still published, still notifies, and
still asks for someone else's attention. Work that is not ready for either
condition stays on the branch, which is exactly what a branch is for.

Caught in `vadgr 0.4.8`: a draft PR was opened with **half the command tree
ported, no e2e run at all, and clippy failing on all three operating systems** -
3 of 16 checks red, from errors the author had already run locally and seen. The
branch was the right place for that work; the PR was not.

**Drive the tool over its real wire, not by importing it.** Importing the module
and calling the function tests the code, not the served tool a client calls: it
skips the MCP server, its schema and the transport. Call it the way a client does
(a `claude -p` subagent with the server mounted), and `claude -p` loads a fresh
server from the current code, so it never tests a stale connection. cua `0.7.0`'s
`app_open` passed its units and an import check while the wire e2e caught a
two-minute hang and an `ok` returned before any window existed.

**Invoke each public product surface exactly as its user does.** For vadgr, put
the tested installation on `PATH`, run `vadgr ...` in a terminal, and test
direct public HTTP plus both current run WebSocket routes separately. Its
installed entry point
can dispatch to Python during migration, but the e2e cannot replace it with
`python -m cli`, a product import, `cargo run` or a private function. For
cua, build the exact PR-head wheel, install it without editable mode outside the
checkout, and mount that environment's `vadgr-cua` entry point in the driving
agent's MCP config. Mobile remains a human session on a physical handset.
Record every resolved command path, artifact hash and tested PR head. Helpers
can prepare state, capture output and generate evidence. They cannot drive the
user flow, choose the agent's actions or replace a public product surface. Such
automation is an acceptance or contract check and never closes an e2e cell.

**Close an e2e with three independent passes**, run concurrently, each with its
**own port, database and daemon** - three observations rather than one run
watched three times. Compare them structurally: every HTTP entry on method,
path, status and **error code**, every CLI entry on argv and exit code, and the
frame type counts per socket. Then read the token counts with the fixture
pinned first, because three identical output counts suggest one result reused
rather than three real calls. **Ask each pass what looked odd, not only whether
its steps passed**: one sweep was entirely green when an agent noticed a single
case taking 15.2s against 0.1-0.8s for every other, which no assertion could
have caught because nothing asserted on duration.

**Drive an e2e with the agent CLI the machine has, and name it in the runbook.**
Codex and Claude Code both run a headless session with their own MCP config, and
either satisfies the method: a **fresh** MCP server started from the session's
own config, the `tool_use` / `tool_result` stream as the verdict, and an isolated
working directory. **Detect the CLI, do not assume it.** Record which one ran and
its version beside the result, because two passes driven by two CLIs are still
two observations, and a reader cannot compare them if the runbook does not say.
A result with no CLI named is a result nobody can reproduce.

**An e2e group proves the tier under real work, not one call per app.** Open the
app and do one action is a smoke test, not an e2e group. A runbook must include
groups that chain several steps and confirm the state structurally between each,
and at least one group that spans two apps: make a thing in one, act on it in
another, and confirm across the boundary. Depth is the bar the suite is judged
on, not the count of apps it touches. A suite of open-and-click-once groups
passes without proving the tier survives a real task.

**Clean install is a mandatory gate, checked on every PR.** A green suite says
the code works where it was built, not that a first-time user can install the
product and start it. Every repo that ships an installable artifact builds that
artifact, installs it alone in a from-nothing container (no build toolchain, no
dev dependencies), starts the entry point, and confirms it serves a readiness
signal, driving the installed product from outside rather than the source tree.
It holds for a Python wheel and a Rust binary alike; only the install step and
the readiness signal differ. cua `0.6.6` shipped because a fresh install of
`0.6.5` could not start at all, and nothing checked a clean install before
publish. A suite is not an install.

**Before calling a runbook finished, run the arithmetic:**

```bash
python3 ../vadgr-docs/scripts/check_e2e.py E2E/<version>/e2e.md
```

It fails on a per-OS matrix row that names no part, and on a `not run` or
`blocked` cell that gives no reason. Both answers are always acceptable; a bare
one is not, because nobody can tell an owed cell from a forgotten one. It also
prints the cell counts every time, so a summary is compared against the cells
rather than trusted. It cannot tell whether a `pass` is true.

**A pass is finished, not paused, and reporting is not a stopping point.** A
checkpoint or a progress summary does not end your turn: write it and keep
driving in the same turn. A pass ends when every cell carries a verdict or a
named blocker. Only a cell that cannot proceed without the owner, or a decision
only the owner can make, ends one early. Stopping to report looks like progress
and is the opposite, because the cells that were never run stay never run.

**Evidence is filed while the pass runs, never assembled after it.** The
evidence directory exists before the first cell, each group files what it
produced at its own boundary, and a group that captured nothing gets a note
rather than a reconstruction.

**Every test suite states what it starts from.** The precondition is the
guarantee, not the reset: every suite declares the state it needs, nothing
inherits silently, and setup happens at the **start** of a group rather than as
the previous group's teardown - a teardown that did not run leaves the next
group dirty, and its failure looks like a product defect. Resetting between
every case is ritual, not rigour.

**Every fix gets a test that fails without it.** Stash the fix, watch it go red,
restore. A test that passes either way tests nothing.

**Never report a result from a command whose exit code you did not read**
(`cmd | head` reports `head`'s), and **a pass with no output is not a pass** - a
sweep once exited `0` five times printing nothing, against a daemon it never
reached.

**Audit once, exhaustively.** Run everything, fix everything, report once.
Fixing, re-checking, finding one more and repeating reads as an endless stream
of problems and is really one incomplete sweep.

**A result you did not produce is not a result.** Never write a number, a
status, a timing, a token count or a table row that no command printed. Evidence
is the artifact - the log, the record, the exit code - and the prose is a reading
of it, never a substitute for it. **A coverage table is generated from a recorded
sweep, never typed.** The failure this stops is not laziness: it is an agent that
could not run a step and wrote what the step would plausibly have said, which is
unfalsifiable at review and makes every real result in the same document worth
nothing. **`not run`, `blocked` and `partial` are always available and always
acceptable**; a fabricated pass never is. If a step could not run, say which,
why, and what would let it run.

**Impossible is a probed verdict, never an impression.** Nothing is declared
fundamental, unfixable or out of scope until it was probed on the real target
and every plausible fix was tried or ruled out with evidence: a different API,
an enablement flag, a workaround at another layer. A "cannot be done" ships
with the probe that showed it, exactly as a pass ships with its log - most
"impossible" failures dissolve under a real probe, and the few true limits are
worth naming only with the probe and the platform's own design notes in hand.
**Hard bugs get the strongest tool before they get a verdict**: under Claude
Code, switching the session or a subagent to the Fable 5 model (`fable`) is
authorized for exactly these investigations, and only for them.

**Implementation is delegated and driven to a finished PR, not hand-held slice
by slice.** A minor's build runs the steps end to end and does not come back
until the PR is review-ready: every slice implemented, the unit suites green,
the README, CHANGELOG and version updated, **the e2e runbook written complete,
and the pass run on a real target OS with its results recorded**. Breaking the
work into internal increments is correct engineering; stopping after one to ask
"should I continue?" is not, because the increments are the builder's to
sequence rather than the owner's to approve one at a time. **Stop for exactly
two things**: a genuine decision only the owner can make - surfaced with the
options and a recommendation - or merge, tag and release.

**The e2e is not a stopping point, and neither is its runbook.** Writing the
runbook is part of the build and so is running it. The owner's approval is a
**review of a written runbook**, which can only happen once one exists, and it
happens without the work stopping. "Next I write the runbook and bring it to you
for approval" is "should I continue?" in different words, and **a gate you have
not reached is not a gate**: it was written after exactly that sentence ended a
`vadgr 0.4.8` report with nothing written and nothing run.

**And the operating system that must pass is the one you built on.** One real
target OS gates opening the PR, and the host that implemented the minor is the
host with the toolchain, the daemon, the state and the defect in front of it.
Building on WSL and opening the PR on somebody else's future pass is the same
deferral wearing a platform label. **You build on it, you pass on it, then you
open the PR**; the other required targets fetch that branch and gate the merge.

**There is no version of this where the implementation is reported and the pass
was not run.** A minor whose e2e has not run is not late, not nearly done and not
awaiting approval: it is **unfinished**, and reporting it as anything else
misreports it. A pass that genuinely cannot run is a blocker with a named cause,
reported as a blocker.

**Pushing to the PR branch is not a gate; merging is.** The PR branch is the
working surface where the e2e runs, so commits go there as they are made, never
held back on the local branch to wait for a nod. The owner's approval gates the
merge, the tag and the release, not the push. A commit kept off the PR to wait
for approval is the mistake: the branch is where the change is reviewed and
tested, and the approval is asked at merge. This holds in every repo in this
family.

**Every branch starts from a freshly pulled default branch.** Three commands, in
this order, every time:

```bash
git checkout master && git pull        # `main` in `vadgr-mobile`
git checkout -b <name>
```

Never from whatever happens to be checked out, and **never from another feature
branch**. The reason is what a squash merge does: it replays the whole diff
against the base, so a branch cut from a feature branch carries that feature's
commits and merging it merges the feature too, under the wrong title and without
its gate.

It happened during `vadgr 0.4.8`: three doctrine pull requests were cut from the
release branch, and squash-merging them put **the entire unfinished CLI into
`master`** under titles about e2e doctrine, ahead of the e2e that was still
running on two operating systems. Nobody read a diff that said so, because the
titles said something else.

**Two checks, both one command.** Before branching, `git status -sb` names the
branch you are about to inherit. Before opening, `git diff --stat <default>...HEAD`
must show only files your subject is about: **a diff carrying work the title does
not mention means the branch point was wrong**, and the fix is to re-cut it from
the default branch rather than to explain it in the body.

**And CI refuses it**, because prose did not stop it the first time.
`scripts/check_branch_point.py` fails a pull request whose branch contains
another open pull request's head: that ancestry is what a branch cut from a
feature branch looks like, and there is no innocent version of it.

**Nothing reaches a default branch except through a pull request, and the docs
repo is not an exception.** Branch, push, open the PR, merge it. That covers
code, plans, design specs, runbooks and **e2e evidence**: evidence is filed on
the same branch as the work it proves and travels in its PR, never pushed
straight to `master` because it is "only artifacts". A direct push has no diff
anyone read, no checks, and no record that a decision was seen before it landed.

It is written here because it was broken wholesale: during `vadgr 0.4.7`, **eight
commits reached `vadgr-docs` master directly** - build specs, the version
register, the patch log, four evidence boundaries and a released-status change -
by more than one agent, while every code change beside them went through a PR.
The docs repo felt like a notebook, and it is the source of truth.

**Complete means complete: a feature is not done while an implementable part is
left as a follow-up.** "Scoped but not built", "one more thing remaining" and
"the last piece is a small fix" are not stopping points, and implementable
leftover work is never handed to the owner as a choice - it is built. The only
things that end the build short of complete are a genuine owner decision or an
approval gate; more work that can be built is never one of them. A part that is
genuinely impossible ships proved-impossible with its probe (see "Impossible is a
probed verdict"), never deferred with a promise.

**Write your replies to the owner in Simplified Technical English, ASD-STE100.**
In Claude Code, set the output style to it; a CLI with no such setting applies
the rules below directly. This applies on every machine and in every repo, so
it is written in each entry point and not in one person's local settings.

The rules:

- Use short sentences. Use 20 words or less for an instruction. Use 25 words or
  less for a description.
- Write one instruction in one sentence.
- Use the active voice. Write "the check found three defects", not "three
  defects were found".
- Use simple and common words. Do not use a technical word when a common word
  is correct.
- Do not use metaphors, idioms or jokes. They are the most frequent defect in
  this project's replies.
- Use the articles "a", "an" and "the".
- Do not use more than three nouns together.
- Use the same word for the same thing every time. Do not use synonyms for
  variety.
- Keep paragraphs short. Use a list when you give more than two items.

**What this applies to and what it does not.** It applies to what you write to
the owner: replies, status reports, and summaries. **It does not change the
documents this project ships.** Their voice is deliberate, and a rewrite of them
is a separate decision that nobody has made.

**No em dashes and no en dashes**, anywhere this project ships: markdown, code
comments, commit messages, PR bodies, and the words on the screen. A colon, a
full stop, brackets or a spaced hyphen does every job. It is checked rather than
remembered:

```bash
python3 ../vadgr-docs/scripts/check_style.py [path ...]
```

**No AI attribution, anywhere.** No `Co-Authored-By`, no "generated with", no
model names - in commits, PR bodies, or generated files.

**PR bodies carry code, tests, user-visible changes and caveats, and nothing
else.** No methodology narration, no design-doc citations. A reviewer must
understand the PR from the PR alone.

**How a minor ends**: `CHANGELOG.md` written in the PR and re-read against the
final diff, the version bumped with it, **`README.md` updated if the minor
changed what it says**, the tag `vX.Y.Z` with notes matching the changelog,
branches deleted local and remote, every repo back on its default branch, then
`PROGRESS.md` updated and the next item named - read from `PLANS.md`'s
iteration table, not decided.

**The README is checked, because it was wrong in all three repos at once.**
`scripts/check_readme_touched.py` fails a pull request that moves a version and
touches no README. It cannot read a README for truth; it can see the shape all
three of those had, which is a version moving alone. **The escape is a sentence,
not a flag**: write `README: nothing changed` in the body, and mean it. A rule
that cannot be answered is one people route around.

**And prose about the product is swept like code.** A README, a design note or a
doc comment naming a runtime the product no longer has is the same defect as a
stale command, and it fails no build. When a release removes something, the sweep
covers the documentation and the comments in the same pull request, not a
follow-up.

**A tag and its release are named one way in every repo**, because six shapes
across three repos is what happens when each release is named freehand: `vadgr
0.4.7`, `v0.4.6 - the Rust execution engine`, `v0.4.4`, `vadgr 0.4.2 - the web
dashboard is gone`, `vadgr-mobile v0.4.1` and one carrying an em dash were all
in use at once. The shape is:

- **the tag is `vX.Y.Z`** and nothing else: no repo name, no suffix, no `release/`
  prefix. The repo is already the context.
- **the tag is annotated, and its message is the release notes**, which match
  the changelog entry for that version. A tag whose subject reads `Merge pull
  request #181 from ...` is a lightweight tag left on a merge commit, and it
  tells a reader nothing about what shipped.
- **the release title is `vX.Y.Z - <what it made true>`**: the tag, a spaced
  hyphen, then a short lowercase phrase naming what the release changed for
  someone using the product. Not the repo name, not bare, and never an em dash.

A bare title makes every reader open the notes to learn anything, and a title
that repeats the repo name spends its only line on something the page already
says.

**Paths in this document are relative to this repo's parent directory**, with
the docs repo cloned beside it. If you cloned it under a different name, use
that name. Nothing here assumes a particular machine, user or absolute path.

## How a change is proven here

The shared block above holds in every repo. What follows is specific to this
repo: where the e2e runbook lives, and the gate that runs before anything is
offered.

- **The e2e runbook lives at `E2E/<version>/e2e.md`**, starts from
  `E2E/TEMPLATE.md`, and its doctrine is `E2E/README.md`, all in this repo.

The gate, before offering anything:

```bash
cargo test
cargo clippy --all-targets -- -D warnings
cargo fmt --check
python3 -m pytest scripts/tests -q      # the repository's own gates
```

**One suite, because there is one product.** Four separate counts lived here
until `0.4.9` retired the tree they belonged to, and two of them were stale for
five releases: they read `596` and `201` after `0.4.4` had deleted the surfaces
those tests covered. A count that is too high reads as a regression to whoever
runs the suite next, which is the opposite of what a count is for. **This is why
the numbers are not written here any more**: `cargo test` prints its own, and a
number in a document is a number nobody re-reads.

One test process at a time wherever anything is shared - two overlapping runs
look exactly like a hung suite. Runs with their own port, database and daemon
may overlap; that is what makes the three-agent e2e close safe.

## Conventions

- Comments explain **why**, not what. Match the surrounding density and voice.
- Branch per minor, PR per minor. Never commit to `master`.
- `CHANGELOG.md` is updated **in the PR**, and the version in `Cargo.toml`
  moves with it.
- **`README.md` is updated in the same PR when the minor changed what it says**,
  and it is the file most people read. A deleted surface, a renamed command, a
  moved directory, a changed install path, a changed dependency floor, or a
  change in what the product **is** all change it. Read the release's own diff
  against it and either edit it or **say nothing in it changed** - the silence is
  the defect. A claim can also rot with no diff touching it, and the one-line
  description is the usual casualty. This repo's went three minors selling
  "AI agents" after the re-scope replaced them, with an install command
  pointing at the repository's former name.
