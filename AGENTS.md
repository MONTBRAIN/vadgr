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
python3 ../vadgr-docs/scripts/check_iteration.py <phase> <iteration>
```

(The script resolves its own paths, so only the path to the docs checkout
matters. Use whatever name it was cloned under beside this repo.) Exit `0` or do
not start. This exists because the rule was written down and broken twice in an
hour.

**4. PR bodies carry code, tests, user-visible changes and caveats.** No
methodology narration, no SOLID tables, no design-doc citations.

## The practices every repo in this family follows

**This section is identical in all four repos, and identical in this repo's
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

**CI is not an e2e pass.** The automated gate builds an environment and runs the
unit suites. It drives no session, calls nothing over the wire and reaches no
glass, so a green CI row on an OS says the suites pass there and **nothing at
all** about whether the product works there. An OS whose only evidence is CI is
marked `not run`, never `pass`, and a runbook's `overall` row never inherits a
gate result: it is the weakest of the parts actually driven on that OS. This
shipped once and was caught in review, with two platforms marked `pass (CI)`
while their own live rows read `not run`. **A suite is not a session.**

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

- **No em dashes** in comments, docstrings, the CHANGELOG, CLI output or a PR
  body. A colon or a spaced hyphen does the job.
- **Every fix gets a test that fails without it.** Stash the fix, watch it go
  red, restore. A test that passes either way tests nothing - one written for a
  gate crash here passed against the unfixed code because the fake never reached
  the failing line.
- **The e2e runbook is run before the PR is offered**, not after. It lives at
  `E2E/<version>/e2e.md`, starts from `E2E/TEMPLATE.md`, and its doctrine is
  `E2E/README.md` - both in this repo. Its coverage tables are **generated from
  a recorded sweep**, never typed.
- **Never report a result from a command whose exit code you did not read.**
  `cmd | head` reports `head`'s status. That produced a confident, wrong claim
  about a CLI exit code in `0.4.1`.
- **A pass with no output is not a pass.** A sweep that invoked the CLI as a
  module exited `0` five times having printed nothing, against a daemon it never
  reached.

**Close the runbook with three independent passes** - three agents running the
sweep concurrently, each with its own port, database and daemon, compared
structurally on status, error code, exit code and socket frame counts. Input
tokens should match across all three and output tokens should differ; three
identical output counts mean one result was reused, not that the run is stable.
Ask each what looked odd, not only whether it passed
(`../vadgr-docs/general/ENGINEERING.md` §6).

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
- A minor ends by updating `vadgr-docs/PROGRESS.md` and naming what is next -
  read from `PLANS.md`'s iteration table, not decided.
