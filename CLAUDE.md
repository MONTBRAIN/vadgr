# vadgr - the machine daemon

A daemon per machine: the native agent loop, the MCP host, gates and policy,
the API the phone talks to, persistence, plus `cli/` - the on-box owner surface.
v2 has no desktop frontend: `frontend/` sits in the tree only until `0.4.2`
deletes it. Build nothing against it.

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

## How a change is proven here

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

The gate, all three suites, before offering anything:

```bash
PYTHONPATH=. python3 -m pytest engine/tests/ -q     # 122
python3 -m pytest api/tests/ -q                     # 551
python3 -m pytest cli/tests/ -q                     # 189
```

One test process at a time wherever anything is shared - two overlapping runs
look exactly like a hung suite. Runs with their own port, database and daemon
may overlap; that is what makes the three-agent e2e close safe.

## Conventions

- Comments explain **why**, not what. Match the surrounding density and voice.
- Branch per minor, PR per minor. Never commit to `master`.
- `CHANGELOG.md` is updated **in the PR**, and the version in `api/config.py`
  moves with it.
- A minor ends by updating `vadgr-docs/PROGRESS.md` and naming what is next -
  read from `PLANS.md`'s iteration table, not decided.
