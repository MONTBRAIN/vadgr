# AGENTS.md

This repo is one of **four** in the vadgr product family. The cross-repo
architecture, design docs, mockups, and the **build conventions all agents must
follow** live in a separate private repo: **`MONTBRAIN/vadgr-docs`**.

**Before working here, clone and read `vadgr-docs` — start with its `AGENTS.md`.**

```bash
gh repo clone MONTBRAIN/vadgr-docs      # the map: ARCHITECTURE.md, design/, MOBILE_DESIGN.md
```

## The four repos (all under MONTBRAIN/)

| Repo | Role | Default branch |
|---|---|---|
| `vadgr-docs` (private) | architecture, design docs, mockups, conventions | master |
| `vadgr` | orchestrator brain (API + CLI + frontend + engine + forge + registry) | master |
| `vadgr-computer-use` | MCP runtime that drives the local machine | master |
| `vadgr-mobile` (private) | Flutter phone app | main |

Clone all four side by side:

```bash
for r in vadgr-docs vadgr vadgr-computer-use vadgr-mobile; do gh repo clone MONTBRAIN/$r; done
```

## Non-negotiable conventions (full detail in `vadgr-docs/AGENTS.md`)

- **No AI attribution** in commits, PR bodies, or generated files.
- **PR bodies = code + tests + user-visible behavior only** — no SOLID tables, no
  doc-section citations, no methodology language.
- **TDD** (tests first); **SOLID applied in code, never named in comments/commits**.
- **E2E verification expected** for `vadgr` / `vadgr-computer-use` changes (not just
  unit tests) — see `vadgr-docs/AGENTS.md` for the exact patterns.
- **Conventional Commits**, no emojis. **Tags use the `v` prefix** (`v0.3.0`).
