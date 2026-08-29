# 0.4.12 - computer use ships inside vadgr: e2e runbook

> **vadgr 0.4.12 implementation:**
> `feature/0.4.12-bundled-cua` at exact tested source `cbf04f3` (product commit
> `cbf04f3`) before the first host passes.
> **vadgr 0.4.12 evidence PR:**
> [vadgr-docs PR #128](https://github.com/MONTBRAIN/vadgr-docs/pull/128).
>
> Every host adds its boundary to #128. After the first real target OS passes
> and branch checks are green, replace the branch/head line with the public
> implementation PR URL before another host starts.

> **Read this whole file and [`../README.md`](../README.md) before running a
> cell.** Evidence is execution output, every owner-dependent cell runs first,
> and no host firewall, DNS, routing, proxy, VPN or network service is changed.

A clean vadgr installation supplies its own pinned, isolated Python 3.12.14 and
`vadgr-computer-use` 0.7.5 payload, launches it without consulting the owner's
Python environment, and leaves the owner machine unchanged outside vadgr's
explicit install and state roots.

> **Status: WSL complete.** Local automated gates are green (179 library
> tests plus integration suites; clippy and formatting exit 0). The
> implementation PR does not exist until one complete real target OS passes.
> **0 open product findings.** Native Linux, Windows and macOS remain owed below.

## The rules

1. Run owner-dependent setup first; announcing it is not running it.
2. Invoke the installed `vadgr` entry point, never `cargo run`, an import or a
   private function. Record its resolved path, hash and exact product commit.
3. One command at a time; capture stdout, stderr and exit code before choosing
   the next command.
4. File each group into the one evidence branch and PR while the pass runs.
5. A cell passes only when both the observation and independently readable
   artifact exist.
6. Fix a discovered defect on this branch with a regression test, rebuild, and
   invalidate every affected earlier cell on every host.
7. Read credentials only from `../.env`; never print values. Run the repository
   secret check before commits and evidence boundaries.
8. Stop only processes started by this pass and remove only the validated,
   isolated roots it created.
9. Never change host networking. A fake executable models a fallback failure;
   it does not block the network.
10. Finish every cell on the current OS with a verdict or investigated blocker
    before reporting.

## Paired surfaces this pass depends on

| repository | released version | what this pass relies on |
|---|---:|---|
| vadgr-computer-use | 0.7.5 | the pinned MCP server and its released `computer-use__get_platform` tool |
| vadgr-mobile | 0.4.5 | nothing; listed because dependency-plan wording contains the checker's conservative client keyword |

No external client repository participates in this machine payload verification.

## Owner and environment requirements

| Requirement | Cells | Availability check before use | Cost, mutation and cleanup |
|---|---|---|---|
| OpenAI API credential and billed account | B1, B3, E1-E3 | `OPENAI_API_KEY` is present in owner-only `../.env`; print only present/absent | Six goal runs maximum for this whole pass; never record the key; delete isolated provider state |
| `gpt-5.6-sol` access | B1, B3, E1-E3 | provider catalog contains the exact id after login | On 2026-08-29 the official price is $4/M input, $0.40/M cached input and $20/M output; each run is limited to one tool call, six turns and five minutes |
| WSL, native Linux, native Windows and macOS target hosts | all host rows | record OS/version and architecture | Each host uses its own isolated install and state roots |
| Linux elevation and explicit consent | LA2 only | `sudo -n true` or owner present for prompt | First dry-run is non-mutating; only the exact printed dependency plan may be approved and applied |
| macOS Accessibility and Screen Recording grants | MA2 only | System Settings shows grants for the private interpreter path | Owner grants/reviews only that interpreter; no automatic Settings changes |
| Disposable roots and payload damage | every cell; WC1 | print validated root paths before use | Destructive only inside that pass's temporary root; restore WC1 from its saved copy, then trash the root |
| Host profiles, user Python state, caches and network configuration | D cells | committed snapshot helper exits 0 | Read/hash only; must be identical before/after outside the isolated vadgr roots |

Official model reference checked 2026-08-29:
<https://developers.openai.com/api/docs/models/gpt-5.6-sol>. It lists Responses,
computer use and MCP support. The operator records the driving CLI and version.

**Owner cells run first on their affected host.** On WSL and Windows the API-key
availability check is enough and needs no click. On native Linux, obtain the
owner's explicit answer to the printed dependency plan before LA2. On macOS,
prepare the private interpreter, then obtain and record the two grants before
MA2. No other cell starts while one of those owner actions can run.

## The approach

Each host starts from a clean temporary home/profile whose `PATH` cannot resolve
`python`, `python3`, `pip`, `uv` or `vadgr-cua`, installs from the exact branch
head through `install.sh` or `install.ps1`, and puts only that installation's
`bin` first on `PATH`. The manifest and child process tree are independent
oracles for what the daemon launches. The run journal is the oracle for tool
dispatch: it must contain one matching `in_flight` and `done` pair for exactly
one `computer-use__get_platform` call.

The fake-path repeat supplies executables named `python`, `python3`, `pip`,
`uv` and `vadgr-cua` that append their name to a sentinel and exit 97. An empty
sentinel proves no fallback. WC1 renames only the isolated payload manifest,
observes unavailable computer use and a healthy control plane, then restores
the same file. D snapshots are taken with the committed helpers before setup
and after cleanup and compared by hash.

## Frozen subject and common commands

For Unix hosts set `E2E_ROOT` to a new absolute temporary directory outside the
repository, `E2E_HOME="$E2E_ROOT/home"`, `VADGR_HOME="$E2E_HOME/.vadgr"`,
`VADGR_STATE_HOME="$E2E_ROOT/state"` and `VADGR_PORT` to a free loopback port.
For Windows use equivalent absolute `$E2ERoot`, `$env:USERPROFILE`,
`$env:VADGR_HOME`, `$env:VADGR_STATE_HOME` and `$env:VADGR_API_PORT` values.
Copy the checkout into `$E2E_ROOT/source`, checkout the recorded commit, and
record `git rev-parse HEAD` before installing. Do not run the installer from
the working checkout because its parent is deliberately rejected as a payload
root.

Unix snapshots:

```sh
E2E/0.4.12/harness/snapshot-unix.sh before "$E2E_ROOT/before.txt"
# run the cells
E2E/0.4.12/harness/snapshot-unix.sh after "$E2E_ROOT/after.txt"
diff -u "$E2E_ROOT/before.txt" "$E2E_ROOT/after.txt"
```

Windows snapshots:

```powershell
& E2E/0.4.12/harness/snapshot-windows.ps1 -Label before -Output "$E2ERoot\before.txt"
# run the cells
& E2E/0.4.12/harness/snapshot-windows.ps1 -Label after -Output "$E2ERoot\after.txt"
Compare-Object (Get-Content "$E2ERoot\before.txt") (Get-Content "$E2ERoot\after.txt")
```

The source installer is the public setup surface. Unix runs
`VADGR_REPO="$E2E_ROOT/source" VADGR_HOME="$VADGR_HOME" ./install.sh`; Windows
runs the checked-out `install.ps1` with the equivalent environment. The Linux
first invocation declines dependency application; LA2 repeats only after the
owner approves. Capture `command -v vadgr`/`Get-Command vadgr`, binary SHA-256,
`vadgr --version`, `lib/cua/payload.json`, the private interpreter version and
the installed cua distribution version, normalising only the temporary root.

Start the installed daemon on the isolated port. Log in with
`vadgr provider login openai --auth api-key`, with the key read by that process
from the owner-only environment, then select or request `openai/gpt-5.6-sol`.
Drive each goal with the installed CLI:

```text
vadgr run --provider openai --model gpt-5.6-sol \
  "Call computer-use__get_platform exactly once. Report only its platform result."
```

Terminate after five minutes or six model turns. Capture the CLI transcript,
API run row, journal, daemon log, process-tree sample and exit code. The exact
run id may differ; no other field is normalised.

## Coverage

| Part | Axes | Cells | Run | Open |
|---|---|---:|---:|---:|
| A: clean installation and ready payload | 4 OS x 3 boundaries | 12 | 3 | 9 |
| B: real tool and hostile PATH | 4 OS x 3 boundaries | 12 | 3 | 9 |
| C: damaged payload isolation | WSL x 1 boundary | 1 | 1 | 0 |
| D: owner-machine non-mutation | 4 OS x 1 boundary | 4 | 1 | 3 |
| E: independent close | 3 isolated WSL agents | 3 | 3 | 0 |
| | | **32** | **11** | **21** |

## Part A: clean installation and ready payload

| # | Precondition and setup | Goal or action | Expected observable and independent oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| WA1 | Fresh WSL root; source at recorded commit; none of Python/pip/uv/cua resolves | Run the source installer with no system-dependency consent | Installed `vadgr` is 0.4.12; manifest pins Python 3.12.14, cua 0.7.5 and this target; private interpreter and distribution report those versions | install transcript/exit, resolution failures, head/path/hash, manifest and version outputs | retain root through WD1 | **pass on WSL**: exact source `cbf04f3`; installed `vadgr 0.4.12`; manifest and private runtime report Python 3.12.14 and cua 0.7.5; all five forbidden host commands were absent |
| WA2 | WA1 installed root | Inspect setup output and host package inventory | WSL applies no OS dependency plan and changes no host package or network state | setup output and before/after package inventory | none | **pass on WSL**: installer applied no system plan and the sorted package inventory is byte-identical before and after |
| WA3 | WA1 root; daemon started | Run `vadgr computer-use status` and read health/settings API | Computer use is enabled, available and ready; daemon stays healthy | CLI/API bodies, daemon log and private child process row | stop only this daemon by pid after group | **pass on WSL**: installed daemon executable verified under the isolated root; CLI says enabled; status reports available on `wsl2`; settings report enabled and ready; health remains healthy |
| LA1 | Fresh native Linux root; same clean-PATH setup | Run source installer and decline dependency application | Same identity/pins as WA1; printed plan changes nothing | same WA1 artifacts plus dry-run plan | retain root through LD1 | not run: native Linux host has not run it |
| LA2 | LA1; owner has read and explicitly approved exact printed plan | Repeat setup with explicit consent | Only the approved system plan is applied; payload remains same pins | consent record without secrets, command output, package diff | retain approved system deps; remove test root later | not run: native Linux owner action and host are outstanding |
| LA3 | LA2 root; daemon started | Run status and APIs | Computer use ready and healthy | same WA3 artifacts | stop own daemon | not run: native Linux host has not run it |
| NA1 | Fresh native Windows profile; no Python/pip/uv/cua resolves | Run checked-out `install.ps1` | Same identity/pins as WA1 with `.exe` and Windows target | PowerShell transcript/exit, Get-Command failures, head/path/hash, manifest/version | retain root through ND1 | not run: native Windows host has not run it |
| NA2 | NA1 installed root | Inspect setup output and registry/package inventories | No system Python, registry, PATH or network change | setup output plus before/after inventories | none | not run: native Windows host has not run it |
| NA3 | NA1 root; daemon started | Run status and APIs | Computer use ready and healthy | same WA3 artifacts | stop own daemon | not run: native Windows host has not run it |
| MA1 | Fresh macOS root; no Python/pip/uv/cua resolves | Run source installer | Same identity/pins as WA1 with macOS target | install transcript/exit, resolution failures, head/path/hash, manifest/version | retain root through MD1 | not run: macOS host has not run it |
| MA2 | MA1 private interpreter path prepared; owner grants Accessibility and Screen Recording first | Run the reported setup/doctor check again | Both grants apply to the private interpreter and setup exits 0; no Settings page was opened automatically | grant-path record and setup output; no unrelated privacy entries | owner may remove grants after MD1 | not run: macOS owner action and host are outstanding |
| MA3 | MA2 root; daemon started | Run status and APIs | Computer use ready and healthy | same WA3 artifacts | stop own daemon | not run: macOS host has not run it |

## Part B: real tool and hostile PATH

| # | Precondition and setup | Goal or action | Expected observable and independent oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| WB1 | WA3 root; API-key login complete; exact billed model selected | Run the bounded goal once | Completed run; exactly one get_platform `in_flight` and matching `done`; real usage present | CLI transcript/exit, run row, complete journal and daemon log | retain provider state for WB3 only | **pass on WSL**: installed CLI completed in six seconds; one `computer-use__get_platform` call returned `wsl2`; one matching successful `done` and two non-zero usage rows were journalled |
| WB2 | WB1; sample the cua child while running or from daemon spawn instrumentation | Read executable and argv and inspect its environment | Executable is below install root; argv contains `-I` and absolute bootstrap; no system executable, `.cu_venv` or `VADGR_CUA_BIN` selects it | process row/argv/environment-name inventory and manifest | none | **pass on WSL**: repeated samples resolve the private CPython and absolute bootstrap below the install root with `-I`; the environment-name inventory carries none of the four forbidden override names |
| WB3 | Fake Python/pip/uv/cua shims first on PATH, sentinel empty | Repeat WB1 exactly once | Same journal result; sentinel remains empty; child path/argv still match WB2 | shim definitions, empty sentinel, transcript, run row, journal, process row | remove shim dir | **pass on WSL**: the eight-second repeat has the same one-call successful journal and real usage; all five hostile shims resolve first, but their sentinel remains zero bytes |
| LB1 | LA3 plus provider login | Repeat WB1 | Same WB1 oracle | same WB1 boundary | retain provider state for LB3 | not run: native Linux host has not run it |
| LB2 | LB1 | Repeat WB2 | Same WB2 oracle | same WB2 boundary | none | not run: native Linux host has not run it |
| LB3 | Hostile shims first on PATH | Repeat WB3 | Same WB3 oracle | same WB3 boundary | remove shim dir | not run: native Linux host has not run it |
| NB1 | NA3 plus provider login | Repeat WB1 | Same WB1 oracle | same WB1 boundary | retain provider state for NB3 | not run: native Windows host has not run it |
| NB2 | NB1 | Repeat WB2 with native process inspection | Same WB2 oracle | executable path, command line and environment-name inventory | none | not run: native Windows host has not run it |
| NB3 | Hostile `.cmd`/`.exe` shims first on PATH | Repeat WB3 | Same WB3 oracle | same WB3 boundary | remove shim dir | not run: native Windows host has not run it |
| MB1 | MA3 plus provider login | Repeat WB1 | Same WB1 oracle | same WB1 boundary | retain provider state for MB3 | not run: macOS host has not run it |
| MB2 | MB1 | Repeat WB2 | Same WB2 oracle | same WB2 boundary | none | not run: macOS host has not run it |
| MB3 | Hostile shims first on PATH | Repeat WB3 | Same WB3 oracle | same WB3 boundary | remove shim dir | not run: macOS host has not run it |

## Part C: damaged payload isolation

| # | Precondition and setup | Goal or action | Expected observable and independent oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| WC1 | WSL WA3 root stopped; copy `payload.json` inside isolated root, then rename original; hostile shims remain | Start daemon; read health/status; attempt bounded run | Control plane remains healthy; computer use is unavailable with payload error; no fallback process starts and sentinel stays empty | rename listing/hash, CLI/API bodies, daemon log, process inventory, empty sentinel | stop daemon; restore exact saved manifest and verify hash | **pass on WSL**: health stayed healthy while computer use became unavailable/not ready; bounded run failed closed; no payload process or shim invocation appeared; restored manifest hash matches exactly |

## Part D: owner-machine non-mutation

| # | Precondition and setup | Goal or action | Expected observable and independent oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| WD1 | WSL before snapshot exists; WA-WC complete and manifest restored | Stop own processes, trash isolated root, take after snapshot and compare | Profiles, user Python state/caches, selected env names and network configuration are unchanged | both raw snapshots, diff exit and process/port checks | trash only isolated root | **pass on WSL**: exact daemons stopped, port free, isolated root moved to trash; snapshot bodies are byte-identical and raw diff changes only the requested label |
| LD1 | Linux before snapshot exists; LA/LB complete | Stop own processes, trash isolated root, snapshot/compare | Same as WD1 except owner-approved LA2 package changes are the only named difference | snapshots, diff, approved package delta, process/port checks | trash test root; retain approved deps | not run: native Linux host has not run it |
| ND1 | Windows before snapshot exists; NA/NB complete | Stop own processes, trash isolated root, snapshot/compare | Profiles, registry Python state, caches, environment and network hashes unchanged | snapshots, comparison, process/port checks | trash only isolated root | not run: native Windows host has not run it |
| MD1 | macOS before snapshot exists; MA/MB complete | Stop own processes, trash isolated root, snapshot/compare | Same as WD1; only the explicitly granted privacy entries may differ | snapshots, diff, grant delta, process/port checks | trash root; owner may remove grants | not run: macOS host has not run it |

## Part E: independent close

Run only after WSL Parts A-D pass. Start three concurrent drivers, each with a
separate copied install, state root, port, database and daemon. Each driver gets
the goal text from WB1, not a prescribed tool call, and records its CLI/version,
transcript, journal and observation of anything odd. Never use blanket process
termination. Compare journals structurally after normalising only run ids:
identical tool name/phase counts, identical input token counts, and plausibly
different output counts.

| # | Precondition and setup | Goal or action | Expected observable and independent oracle | Evidence boundary | Cleanup | Status |
|---|---|---|---|---|---|---|
| E1 | Isolated close root/port/database A; provider ready | Independent agent drives WB1 goal once | One real get_platform call, completed journal and usage; driver reports anything odd | driver transcript/version, CLI output, journal, API row, process identity | stop only A pid; remove A root after comparison | **pass on WSL**: shared-epoch run `run-3502c88d7b2d4574a959931f291f9327`; one successful call/result, real usage, nothing odd, exact daemon stopped |
| E2 | Isolated close root/port/database B; provider ready | Independent agent drives WB1 goal once concurrently with E1/E3 | Same E1 oracle, independently produced | same E1 boundary for B | stop only B pid; remove B root after comparison | **pass on WSL**: shared-epoch run `run-2f913bd51f1d4233b65d61adf9c99625`; same successful structure and usage; a post-run harness quoting error was independently repaired against retained artifacts; no product oddity |
| E3 | Isolated close root/port/database C; provider ready | Independent agent drives WB1 goal once concurrently with E1/E2 | Same E1 oracle; structural comparison passes and output counts are not suspiciously identical | same E1 boundary for C plus generated structural comparison | stop only C pid; remove C root | **pass on WSL**: shared-epoch run `run-e567276ace734ef4b33be9ef44ce3a04`; all command intervals overlap with 10.3 ms launch spread; unique runs/daemons and distinct first-response hashes prove identical output counts are deterministic, not reused |

## Per-OS results

| Part | WSL | Linux | Windows native | macOS |
|---|---|---|---|---|
| A: clean installation and ready payload | pass: WA1-WA3 on exact source `cbf04f3` with cua 0.7.5 | not run: host outstanding | not run: host outstanding | not run: host outstanding |
| B: real tool and hostile PATH | pass: WB1-WB3, one real call both normally and under hostile PATH | not run: host outstanding | not run: host outstanding | not run: host outstanding |
| C: damaged payload isolation | pass: WC1 failed closed without fallback and restored exact manifest | Not-Needed: WSL covers manifest isolation in shared code after per-OS spawn is proven in B | Not-Needed: WSL covers manifest isolation in shared code after per-OS spawn is proven in B | Not-Needed: WSL covers manifest isolation in shared code after per-OS spawn is proven in B |
| D: owner-machine non-mutation | pass: WD1 snapshot body unchanged after trashing isolated root | not run: host outstanding | not run: host outstanding | not run: host outstanding |
| E: independent close | pass: three isolated shared-epoch runs overlap and match structurally | Not-Needed: repeatability closes the frozen payload once after all OS-specific launch branches are completed | Not-Needed: repeatability closes the frozen payload once after all OS-specific launch branches are completed | Not-Needed: repeatability closes the frozen payload once after all OS-specific launch branches are completed |
| **overall** | **pass: all eleven WSL cells completed with no product finding** | **not run: native Linux outstanding** | **not run: native Windows outstanding** | **not run: macOS outstanding** |

## Evidence and remote-host handoff

Evidence lives only in `vadgr-docs` branch `evidence/vadgr-0.4.12`, PR #128,
under `e2e_evidence/vadgr-0.4.12/<date>-<os>/`. Create that OS directory before
its first cell. At each part boundary copy raw command output, exits, hashes,
manifest, process rows, API bodies and journals; run the secret scan; commit and
push that boundary immediately. A group with no artifact gets a note and cannot
pass.

| operating system | filed evidence boundary |
|---|---|
| WSL | `e2e_evidence/vadgr-0.4.12/20260829-wsl/part-a/` through `part-e/`, latest evidence commit `e4740f5` |
| native Linux | not run: host outstanding |
| native Windows | not run: host outstanding |
| macOS | not run: host outstanding |

A fresh OS agent needs only this file and the committed harness. It must:

1. pull the implementation branch and evidence branch, read both E2E documents,
   and verify the frozen commit or later PR head named at the top;
2. verify its owner prerequisite first (Linux consent or macOS grants), without
   exposing credentials;
3. use a unique temporary install/state root and port, capture the before
   snapshot, and drive its A, B and D rows in order;
4. run every public command through the installed entry point, file raw evidence
   after each part, and write only its own OS column;
5. stop only its own pid, prove its port free, remove only its isolated roots,
   run secret/attribution/E2E checks, and push to the two existing branches.

Prerequisites that can block later work are deliberately named up front:
internet access is needed to fetch pinned archives/wheels and reach OpenAI;
Rust is needed by the source installer; native Linux needs explicit package-plan
consent; macOS needs grants for the private interpreter; and the billed model
must appear in the connected provider catalog. None authorises a host-network
change.

## Findings

No product findings on WSL. Two successful close attempts were rejected because
their command intervals did not overlap; the accepted shared-epoch attempt is
filed with the rejected intervals and structural comparison in Part E evidence.
