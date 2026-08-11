# vadgr - the machine daemon

A daemon per machine: the native agent loop, the MCP host, gates and policy,
the API the phone talks to, persistence, plus `cli/` - the on-box owner surface.
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
  --include=*.py --include=*.md . | grep -v "\.venv\|AGENTS.md\|CLAUDE.md"
```

**The exception, stated so it is not guessed at: this file and `AGENTS.md` name
the private docs on purpose** - they are the entry point, and a pointer that
cannot name what it points at is useless. The ban is on everything a stranger
reads as the product: code, comments, docstrings, test names, the CHANGELOG and
PR bodies. Those cite the substance, never the document.

**2. No AI attribution, anywhere.** No `Co-Authored-By`, no "generated with", no
model names - in commits, PR bodies, or generated files.

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

**The e2e is run before the PR is published, and the owner reviews the results,
not a plan.** Whoever builds the change runs the e2e the feature needs - a browser
change against real sites, a desktop or structured change against real
applications, never a mock - and ships the results in the PR. There is no
approve-the-runbook-before-it-runs step: the owner reviews the results and asks for
changes if they do not convince. A PR that claims a feature works with its e2e left
unrun is incomplete.

**Drive the tool over its real wire, not by importing it.** Importing the module
and calling the function tests the code, not the served tool a client calls: it
skips the MCP server, its schema and the transport. Call it the way a client does
(a `claude -p` subagent with the server mounted), and `claude -p` loads a fresh
server from the current code, so it never tests a stale connection. cua `0.7.0`'s
`app_open` passed its units and an import check while the wire e2e caught a
two-minute hang and an `ok` returned before any window existed.

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
the README, CHANGELOG and version updated, and the e2e runbook drafted. Breaking
the work into internal increments is correct engineering; stopping after one to
ask "should I continue?" is not, because the increments are the builder's to
sequence rather than the owner's to approve one at a time. **Stop for exactly
two things**: a genuine decision only the owner can make - surfaced with the
options and a recommendation - or a defined approval gate, which is running the
e2e (its runbook is approved before it runs) and merge, tag and release.

**Pushing to the PR branch is not a gate; merging is.** The PR branch is the
working surface where the e2e runs, so commits go there as they are made, never
held back on the local branch to wait for a nod. The owner's approval gates the
merge, the tag and the release, not the push. A commit kept off the PR to wait
for approval is the mistake: the branch is where the change is reviewed and
tested, and the approval is asked at merge. This holds in every repo in this
family.

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

**Paths in this document are relative to this repo's parent directory**, with
the docs repo cloned beside it. If you cloned it under a different name, use
that name. Nothing here assumes a particular machine, user or absolute path.

## How a change is proven here

The shared block above holds in every repo. What follows is specific to this
repo: where the e2e runbook lives, and the gate that runs before anything is
offered.

- **The e2e runbook lives at `E2E/<version>/e2e.md`**, starts from
  `E2E/TEMPLATE.md`, and its doctrine is `E2E/README.md`, all in this repo.

The gate, all three suites, before offering anything:

```bash
PYTHONPATH=. python3 -m pytest engine/tests/ -q     # 122
python3 -m pytest api/tests/ -q                     # 429
python3 -m pytest cli/tests/ -q                     # 141
(cd rust && cargo test)                             # 40
```

The api and cli counts read `596` and `201` until `0.4.5`, which were their
pre-deletion sizes: `0.4.4` removed the surfaces those tests covered and nobody
moved the numbers. A count that is too high reads as a regression to whoever
runs the suite next, which is the opposite of what it is for.

One test process at a time wherever anything is shared - two overlapping runs
look exactly like a hung suite. Runs with their own port, database and daemon
may overlap; that is what makes the three-agent e2e close safe.

## Conventions

- Comments explain **why**, not what. Match the surrounding density and voice.
- Branch per minor, PR per minor. Never commit to `master`.
- `CHANGELOG.md` is updated **in the PR**, and the version in `api/config.py`
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
