# 0.5.0 - the product is installable: E2E runbook

> **Implementation PR:** `https://github.com/MONTBRAIN/vadgr/pull/239` from
> `feature/0.5.0-distribution` at
> each observation's recorded source commit. Later branch commits include
> product repairs and signing workflow changes, not only policy or evidence.
> No signed candidate is frozen yet. Freeze the exact current source and
> artifact hashes before each new live group. The implementation PR opens
> after the first required real target pass and green source checks.
> **Private evidence PR:** `https://github.com/MONTBRAIN/vadgr-docs/pull/176`.
> Do not create a replacement PR.
>
> **Status: unsigned functional qualification in progress.** Applicable
> functional assertions against exact release-equivalent unsigned artifacts are
> the formal merge gate. No held signed candidate exists yet. Signature, trust,
> notarization, attestation, adoption and promotion assertions remain the
> post-merge release gate.

This runbook proves that a published Vadgr release installs, operates, repairs,
updates, rolls back and uninstalls without a checkout, system Python or separate
CUA installation. Read this file and [the shared rules](../README.md) completely
before the first action. Raw evidence belongs only in the private evidence PR.
The negative control records **terms declined** and proves zero mutation.

## Fixed subject and evidence boundary

Before pre-merge functional work, record the implementation commit plus each
release-equivalent unsigned artifact's target, inventory, byte size and SHA-256.
Every host result names its exact artifact. Before post-merge trust work, record
the merged commit, protected candidate workflow run, held artifact IDs, names,
byte sizes and SHA-256 values. Record the signed tag only after it exists.
Release promotion must preserve the held candidate bytes. A rebuild invalidates
the affected assertions on every host. Public status contains outcomes and
finding identifiers only. Raw
installer logs, screenshots, signature reports, journals and wire responses stay
under the private `e2e_evidence/vadgr-0.5.0/HOST_NAME/` boundary. Redact no failure;
prevent credentials and owner-private paths from entering the capture.

## Paired surfaces this pass depends on

| repository | released version | exact released subject | what this pass relies on |
|---|---|---|---|
| vadgr-mobile | 0.4.6 | `c7c17759bcce4080f6e3d1a9f42a02db93e9aaf5` | account-independent pairing, machine display and run observation used by the physical-phone cells |
| vadgr-computer-use | 0.7.8 | `af347a0cdd782626a84542f7fd781e23c87d87d2` | the currently released screenshot runtime, browser discovery and released-broker upgrade handoff baseline |

The final candidate advances the bundled profile payload to CUA 0.7.9. Its
profile product source is `c7b25b66bbc5e2165d510ca3ba31083044c70557`,
merged by `5a7a305df05f787d375ed38e5cd35a8f0bb2805d`. The held profile catalog
binds the exact per-platform wheels. Those bytes must pass the CUA adoption
cells and become the CUA 0.7.9 release before the Vadgr candidate is promoted.

## Development qualification before the candidate

Windows cloud access was separately qualified with one inert EXE in Actions
run `35168877860`, at `75c70d1307e969dc5541edd74f68322d29e3b07e`.
Its public certificate SHA-256 matched an independent issued-certificate DER.
That test is not a pass for W03 or for the protected candidate workflow. It uses
`scripts/signing/publisher.json` as its reviewed public identity, with
CodeSignTool signing and independent Windows verification. The `.pyd` staging
name, MSI and Burn layers remain subject to W03 on the final candidate.
No production signing run is authorized by this development qualification.
The default-branch `candidate.yml` requires validated source, reviewed legal
inputs, a protected `candidate-authorize` approval, durable one-use signing
claim, and a separate `candidate-windows` approval before native signing. The
legacy tag-triggered `release.yml` is deliberately disabled; it is not a way to
sign or promote a candidate. An exact held-artifact promotion path is required
before any production release.

### Producer shape and release gates

Vadgr 0.5.0 uses the **post-merge protected candidate** lifecycle. The open
implementation PR produces exact release-equivalent unsigned artifacts and
never receives a production signing credential. The protected `candidate.yml`
workflow runs from `master` and accepts only the exact merged protected
default-branch commit as product source.

The implementation PR may open after the ordinary first-host functional pass
and green source checks. Every required functional host assertion, finding and
PR check gates merge. Signing-dependent assertions do not gate PR opening or
merge because no eligible production signing subject exists before merge.
Merge authorizes protected CD to create one held, non-public candidate. It does
not authorize a tag or release.

After merge, run only the signature, trust, notarization, attestation, adoption
and exact-byte assertions which require the held candidate. Repeat functional
assertions only when signing or final packaging changed the behavior they prove.
Publication then promotes those same qualified bytes without rebuilding or
re-signing. It compares inventory, provenance, hashes and signatures before
publication and again after public download. Never use an unsigned result as a
signing pass.

The host lead runs functional qualification against exact release-equivalent
unsigned artifacts before merge. Use isolated test state and label every result
with its functional or trust lane. CUA 0.7.5 proved earlier
console, daemon and released computer-use integration. It
does not prove the final package contains CUA 0.7.9. An unsigned local package may
prove installer flow and lifecycle behavior and W03's expected unsigned-state
observation, but it cannot satisfy W03's publisher, chain or timestamp oracle,
or any oracle that specifically requires a signature, immutable candidate,
clean host or published release.

Run every unaffected action and oracle now. Defer only the unavailable assertion
inside a cell, then rerun that assertion and any behavior it can affect against
the final candidate. Development findings are real implementation findings and
must be fixed before the candidate is produced.

### Qualification lanes

The cell number does not decide whether work waits for signing; the individual
oracle does. Mixed cells are split below and retain every original assertion.

| lane | assertions in this minor | execution rule | completion meaning |
|---|---|---|---|
| pre-merge functional qualification | `W01` terms/zero-mutation and ordinary unsigned install observations; `F01`; `W03` unsigned-state observation; `W04`; `W05`; the restart, private-runtime inventory and truthful unavailable-runtime slices of `W06`; the reachable download/failure-preservation slice of `W07`; `W08`; the first-release failed-update preservation and truthful unavailable-rollback slices of `W09`; isolated preservation, reinstall and explicit purge from `W10`; functional slices of `M01`, `M03` through `M06`, `L01` through `L06` and `S01` through `S06`; `O1`; `O2`; `C1` | run against exact release-equivalent unsigned artifacts on every required available host; absence of a signing identity is not a blocker | formal functional merge qualification; never a signature, trust or release pass |
| post-merge trust qualification | `W02`; `W03` publisher, chain and timestamp assertions; the authorized bundled-CUA task slice of `W06`; the verification, post-verification staging, dependency, daemon-stop, commit and health-check slices of `W07`; `W09` retained-artifact signature assertions; `M02`; `M03` Developer ID, hardened-runtime, notarization, staple and designated-requirement assertions; signed identity slices in `M05`; final vehicle and installed-payload trust assertions on Linux/WSL where named | run only against the immutable held candidate from the exact merged commit | required before tag and release; these remain owed until that subject exists |

No accessibility, phone, transport, isolated lifecycle, offline or cleanup
assertion waits merely because its platform cell also contains a signing
assertion. Evidence and status name the exact slice that ran.

### Pre-merge package production

Every native host must build and qualify the release-equivalent unsigned
vehicle registered in `packaging/distribution-matrix.json` before merge:

- macOS uses `Vadgr-0.5.0-macos-x86_64.pkg` or
  `Vadgr-0.5.0-macos-arm64.pkg`, without Developer ID signing or notarization;
- native Linux uses `Vadgr-0.5.0-linux-x86_64-installer.AppImage` or
  `Vadgr-0.5.0-linux-aarch64-installer.AppImage`, with development integrity
  metadata but without the protected production attestation;
- WSL uses its target-specific release-equivalent `.tar.gz` asset set.

A `.deb`, loose checkout, source binary, system Python environment, earlier
package or another platform's artifact is not a substitute. Adding `.deb`
would change the approved distribution design and would qualify only the
package-manager families that consume it; this minor's native Linux vehicle is
AppImage.

If `packaging/inputs/<target>`, the reviewed wheelhouse, `dist/payload`, or a
credential-free producer is absent, that is a pre-merge implementation finding.
The host agent must repair or create the packaging on
`feature/0.5.0-distribution`, add regression coverage, run the affected gates,
build the exact unsigned vehicle, record its inventory and SHA-256, and resume
the affected cells. It must not wait for `candidate.yml` or a protected artifact
whose lifecycle begins only after merge. A genuinely missing owner-reviewed
non-secret input is reported by exact path only after every independent repair
is complete. Production signing, notarization, timestamping and keyless
attestation remain post-merge trust work.

W11 belongs to pre-merge functional qualification. It requires fresh native
producer observations after the ARM64 base-runtime change, not a signing identity.

This is Vadgr's first native installer generation. No verified pre-0.5.0 native
vehicle exists, so a successful update followed by a successful rollback cannot
be created honestly in this minor. `W09` therefore proves the first-release
state and failure-preservation behavior here. The first subsequent native
update must run the positive update-and-rollback path using the published 0.5.0
vehicle as its real predecessor. That later obligation does not block the 0.5.0
implementation merge or manufacture a synthetic predecessor.

## Native console driving

The host lead drives every automatable installer, console, CLI and connected
phone action. Use the host platform accessibility tree. Use Windows UI
Automation through AccessKit on Windows. Use macOS Accessibility on macOS. Use
AT-SPI on native Linux. Take an exact app-only capture through the host-native
path: `PrintWindow(PW_CLIENTONLY)` under a per-monitor-aware DPI context on
Windows; `SCScreenshotManager` with an
`SCContentFilter(desktopIndependentWindow:)` on macOS; one XDG Desktop Portal
ScreenCast WINDOW source and its PipeWire stream on Wayland; or the target
window ID and XComposite window pixmap on X11. Prove once per host that capture
works while another application has focus. A focused capture, desktop capture,
monitor capture or crop from either is not a substitute. If exact unfocused
capture is unavailable, leave the visual assertion owed. After every action,
reacquire the accessibility elements, inspect the app-only capture against the
approved mockups, and verify the result through the API, process, package,
filesystem or journal oracle named by the cell.
The bundled Vadgr CUA payload is not the Windows installer or console driver.
Use it only for a cell that explicitly runs a product computer-use task. Its
screenshot, pointer, OCR and browser tools do not satisfy the native Windows UI
Automation oracle.

The owner acts only when the operating system protects the interaction from
automation or a physical camera must scan a QR code. The runbook's isolated
test-state cells authorize their named destructive operations; the agent drives
their confirmations through accessibility. Prepare the exact state first. Give
the owner one precise action and the visible completion result, then resume control. Do not ask
the owner to click ordinary controls, type a pairing code, take screenshots,
read the UI or report a machine oracle.

### Virtualized native Linux and the host ADB bridge

A supported Linux guest that runs the package, desktop and product processes
directly is valid native functional coverage. Record it as virtualized native
coverage. Record the hypervisor, guest release, virtual hardware, architecture,
desktop and display protocol. Do not call it bare-metal coverage. Hardware-
specific behavior, another architecture and an unavailable X11 or Wayland
session remain `not run` with their exact reasons. WSL, a container and a
Windows-mounted checkout do not qualify under this rule.

When Android USB is attached to the VirtualBox host instead of the guest, use
the host ADB server before declaring the phone unavailable. The host operator
runs these commands in a dedicated terminal from Android Platform Tools:

```bash
adb kill-server
adb -a start-server
```

`-a` exposes the ADB client socket beyond host loopback. Use it only for this
short test on a trusted host network and restore loopback-only operation during
cleanup. Do not change the host or guest firewall, DNS, routing, proxy, VPN,
Tailscale or other network service.

In the Linux guest, stop only the guest-local server before selecting the host
socket, derive the VirtualBox NAT gateway, and verify the device:

```bash
unset ADB_SERVER_SOCKET
adb kill-server || true
VM_HOST_GATEWAY="$(ip route show default | awk 'NR == 1 { print $3 }')"
test -n "$VM_HOST_GATEWAY"
export ADB_SERVER_SOCKET="tcp:${VM_HOST_GATEWAY}:5037"
adb devices -l
```

The usual VirtualBox NAT gateway is `10.0.2.2`. Require exactly the intended
phone to appear in `device` state, not `offline` or `unauthorized`. Keep
`ADB_SERVER_SOCKET` set for every ADB command in the pass. Do not start a local
guest server afterward, and do not run `adb kill-server` while the variable
points at the host. Evidence records that the authorized physical device was
present but omits its serial and other private identifiers.

After the phone cells, the host operator restores the host's previous ADB mode:

```bash
adb kill-server
adb start-server
```

The guest then runs `unset ADB_SERVER_SOCKET`. A failed remote-socket probe is
a host-bridge prerequisite failure, not proof that the phone is absent. Ask the
owner only to start or restore the host server, approve an Android trust prompt,
reconnect the cable, or aim the already-open scanner when one of those protected
physical actions is actually required.

An enabled control must perform its documented action. A control unavailable
because of current state must be disabled and state that reason beside it. A
visible control for a later release must be disabled and label the exact enabling
minor, for example `Available in 0.6.0`. An enabled no-op, an inaccessible
control, or a future control without the exact version label fails the applicable
cell.

| visible control group | accessible role and action | 0.5.0 state | machine oracle | cells |
|---|---|---|---|---|
| Machine, Providers and Settings navigation | named tab, invoke/select | enabled | visible view heading | W04, O2 |
| Connection details | named read-only text | Built-in endpoint ID, direct addresses and relay state; Tailscale advertised host and port when available; unavailable transports say so | `GET /api/machine` transport diagnostics | W05, O2 |
| Restart Vadgr | named button, invoke | enabled when no operation is pending | daemon PID and health transition | W06 |
| Manage providers, Connect, Disconnect, Refresh models and Make default | named button, invoke | enabled only when the provider state permits it; the surrounding status gives the disabled reason | provider API and default-model state | F01, O2 |
| Edit machine, grant checkboxes, Save changes and Cancel | named button or checkbox, invoke/toggle | required grants stay checked and are labeled `required` | machine API and database after restart | W04, O2 |
| Pair device, typed code, QR code, Unpair, Keep paired | named button or text field, invoke/set value | Pair device is disabled until a default provider is ready and the provider card states why | device API, transport row and live socket | F01, W05, O2 |
| Launch at login, update, legal, rollback, repair and uninstall | named switch or button, toggle/invoke | enabled from the installed package receipt and available retained artifacts; every disabled row states its current-state reason | package receipt, launch entry, versions and owned-file hashes | W07 through W10, O1, O2 |
| Keep installed, delete-owner-state checkbox and Uninstall Vadgr | named button or checkbox, invoke/toggle | destructive action remains disabled until its typed confirmation is exact | package and isolated state-root inventory | W10, O2 |

The approved 0.5.0 mockups contain no control deferred to a later minor. If a
later implementation adds one, its disabled exact-version label is part of both
the visual and accessibility oracle.

## Owner and external prerequisites

- Before any formal candidate cell: owner-approved Version 1.0 terms bytes; final legal
  bundle; reviewed verifier and trusted-root hashes, keyless attestation bundle;
  protected
  candidate run; immutable artifacts and attestations; private evidence PR.
- Windows: clean x64 and arm64 targets where supported, administrator approval,
  Smart App Control target, issued public Authenticode identity and approved
  secure signing route. Signing operations may be billed. Never retry them
  automatically.
  The protected `candidate-windows` environment holds `ES_USERNAME`,
  `ES_PASSWORD` and `ES_TOTP_SECRET`; `candidate-authorize` separately gates
  the exact feature source and one-use claim. Both require the configured owner
  review and permit only trusted default-branch deployments, not `v*` tags.
  Confirm names and protection without reading values. Review the displayed
  per-architecture quota before approving the signing job. One failed or
  uncertain attempt stops the job; do not rerun it.
  The Java runtime and both vendor archive hashes must pass before credentials
  are supplied. CodeSignTool reads credentials in-process, never from OS argv.
- macOS: clean Intel and Apple Silicon hosts, administrator approval, active
  Apple Developer membership, Developer ID Application and Installer identities,
  notarization permission, and an owner present for Login Items, Accessibility
  and Screen Recording. The prior feature-branch macOS signer is disabled:
  its scripts could run with Developer ID credentials. Do not request approval
  or mark M02/M03 signed until a reviewed default-branch trusted signer accepts
  exact held artifacts and produces the required manifest bundle. The host must
  build the release-equivalent unsigned PKG and run its functional cells before
  merge; a missing unsigned PKG or credential-free producer is an implementation
  finding, not a reason to wait for that signer.
- Linux: clean x86_64 and aarch64 targets, X11 and Wayland sessions, optional
  FUSE, and separate approval before a distro package manager changes anything.
  The host must build the registered release-equivalent AppImage before merge;
  a missing AppImage, package input or credential-free producer is an
  implementation finding. Do not wait for the protected candidate workflow and
  do not substitute a `.deb`.
- WSL: clean x64 and arm64 distributions where supported, including an Ubuntu
  22.04 WSL baseline with glibc 2.35 and a current Ubuntu distribution. An
  older glibc or musl-only fixture must refuse installation before mutation.
  No GUI, service, autostart or Windows mutation is permitted.
- Mac and native Linux leads: read the merged release design before preparing
  a candidate. Do not generate a permanent offline manifest key or request
  encrypted key backups. The candidate now requires an immutable
  `release-manifest.json.bundle.jsonl` from the protected GitHub signer,
  verified against the independently pinned root and exact workflow identity.
  On macOS, keep Developer ID signing, notarization and the stable CUA helper
  requirement; the manifest bundle does not replace any native signature.
  On Linux, verify the bundle offline before trusting AppImage hashes, and
  repeat the root, workflow, manifest and artifact tamper matrix on both GUI
  backends. Neither host marks signed cells complete from unsigned evidence.
- Functional cells: a test provider account with bounded billing, one physical
  phone where pairing is named, and permission for one harmless screenshot task.
  Supply secrets only through the repository-approved local secret input. Never
  capture their values.

## Billed model selection for this pass

Before each billed group, use live internet access to read the providers'
current official model and pricing pages and intersect them with the
authenticated catalog. Choose the cheapest model that satisfies the cell's
tool, image and continuation requirements. Current cost targets are the Claude
Sonnet, GPT Luna at medium reasoning and Gemini Flash families; GPT Terra is the
OpenAI fallback only for a capability Luna lacks. These are examples, not
frozen ids; a newly launched cheaper capable model replaces them. Fable, Sol,
Opus and equivalent frontier tiers are not allowed for setup, navigation,
screenshots, smoke tasks or ordinary CUA checks. Before any frontier call, the
evidence must already
contain the cheaper model's capability failure from the same cell, the written
escalation condition that fired, and a separate hard cost ceiling. A persisted
expensive default is changed before the first routine billed call.

## Part H: protected owner boundaries executed first

Each host lead reaches these boundaries before unrelated unattended cells. Only
prerequisite setup needed to make the protected or physical interaction appear
may run first. The host lead remains responsible for all surrounding actions and
oracles. Windows executes only the Windows rows in this session.

| cell | operating system and architecture | owner/environment requirements | precondition | agent setup | exact owner action | visible completion result | evidence boundary | cleanup | cost, accounts, devices and permissions | result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| W02 | Windows x64 and arm64 where supported | owner is present only if Windows presents a protected UAC prompt | W01 and the pre-install part of W03 pass | start the verified setup, accept terms and continue until the protected prompt appears | Confirm that the prompt names the expected Vadgr publisher, then choose **Yes**. Do nothing if no prompt appears. | setup resumes and shows truthful installation progress | private Windows boundary; capture no protected desktop image | keep installation for Windows cells | one administrator approval if requested; no provider cost | not run: final signed setup is unavailable; no protected prompt may be trusted yet |
| F01 | each native GUI host | owner holds the physical phone with camera permission | installed console and default provider are healthy; agent has opened the prepared QR screen | agent confirms ADB, launches Vadgr Mobile, selects the intended Built-in pairing flow, grants automatable permissions, leaves its live scanner open, enters any provider secret through masked UI without capture, and leaves the desktop QR fully visible | Aim the already-open Vadgr Mobile scanner at the visible desktop QR. Stop when the prepared mobile app shows the machine name. | agent reads the mobile result directly, verifies the console device, provider API, daemon lines and transport rows, then drives revoke and typed-code pairing through ADB | matching private host boundary | keep the typed-code device paired for transport cells | phone and camera permission; provider API use may be billed | Windows x64 pre-merge functional pass at `24ae14a`: QR/Built-in direct pairing succeeded after the owner only aimed the prepared scanner. The agent then enabled the phone's existing Tailscale connection and completed the typed-code/Tailscale fallback through ADB. Mobile named the selected transport and the alternate Built-in route; no provider call, host-network mutation, pairing secret or private endpoint was retained |
| M02 | both macOS architectures | owner controls Login Items, Accessibility and Screen Recording | signed package is ready; Terminal and Python grants remain absent | drive installer and console until each protected system prompt or Settings row appears | Approve the Vadgr login item. Deny, then grant, Accessibility and Screen Recording only to the displayed Vadgr Computer Use identity. Stop when System Settings shows both grants enabled. | grants attach to `com.montbrain.vadgr.cua`, not Terminal or Python | private macOS boundary; never export the TCC database | leave grants for M06 | Apple membership, administrator and privacy permissions | not run: signed and notarized macOS package is unavailable |
| L02 | native Linux x86_64/aarch64, X11 and Wayland | owner can approve a package-manager prompt if it appears | release-equivalent AppImage is ready and FUSE dependency is absent | drive install until the protected package prompt appears | Verify the prompt names only the documented FUSE dependency, then approve it. Do nothing if no prompt appears. | installer resumes its visible phases | private Linux boundary | keep installation | separate package-manager approval | pre-merge functional assertion: run against the exact release-equivalent AppImage; no signing identity is required |

## Part W: Windows cells

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions | result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| W01 | Windows x64, then arm64 | clean desktop; no owner action | no Vadgr product, state or launch entry | agent records product paths, HKCU Run, Start menu and isolated state-root inventory, then verifies fixed artifact hashes | agent opens setup through accessibility, inspects terms, leaves acceptance clear and invokes decline | before/after product paths, HKCU Run, Start menu and state-root inventory | setup closes and creates nothing | private Windows boundary: app-only captures plus inventories | delete download only after evidence is filed | no signing call; elevation must not appear before acceptance | Windows x64 pre-merge functional pass at `24ae14a`: exact setup terms and disabled acceptance were inspected; accessibility drove Decline and its owned native confirmation with zero package, state or launch mutation; the same bytes then installed with truthful progress and explicit success and ordinary launch returned healthy. ARM64 installed-product behavior is unavailable; W11 covers only its native producer/observer path |
| W03 | Windows x64, then arm64 | clean Smart App Control target | W02 not yet installed on fresh snapshot for the pre-install half | obtain setup, MSI and manifest from immutable release | agent runs `Get-AuthenticodeSignature` and SignTool verification on setup and MSI; after W02, repeat on cached Burn engine/uninstaller and every installed PE | valid chain, expected publisher and timestamp on each named file | every required vehicle and installed executable is valid; one unsigned layer fails | private Windows signature report | retain clean state for W02 after pre-install verification | no new signature operation | post-merge trust assertion: not run because no held signed candidate exists. The expected unsigned-state observation is recorded separately and does not pass this assertion |
| W04 | Windows x64/arm64 | none beyond installation | release-equivalent unsigned install healthy | record `vadgr machine --json`, API machine and console | edit name, role prompt, autonomy mode, workspace and available grants in console; repeat selected edits with `vadgr config` | all three reads and database persistence after restart | one full machine snapshot; read-only fields rejected; no-op is idempotent | private Windows machine/API capture | restore original settings | none | Windows x64 pre-merge functional pass carried forward through `24ae14a`: the final changes after the rerun affect only console status copy and E2E driving, not machine reads, edits, persistence or validation. ARM64 installed-product behavior is unavailable |
| W05 | Windows x64/arm64 | physical phone connected and visible to ADB | F01 paired | agent confirms ADB state and keeps both transports available | agent uses accessibility and ADB to inspect devices, the Machine view's read-only Built-in endpoint/direct/relay details, Tailscale advertised host and port, and connected state, then cancel and confirm revoke | `GET /api/machine` transport diagnostics, API device rows and live socket closure | the accessible Machine values equal the safe diagnostics; unavailable transports say so; long values wrap at the minimum window without horizontal overflow; cancel keeps the device; confirm revokes and disconnects it | private Windows device and app-only capture | agent pairs one device for later task | phone required; no owner action | Windows x64 pre-merge functional pass at `24ae14a`: mobile reported Tailscale connected with Built-in also available; the console and loopback API reported both transports available; the existing minimum-width wrapping observation remains unaffected. Accessibility-driven cancellation kept the device, confirmation removed the only API device row, and no secret-bearing surface was filed. ARM64 installed-product behavior is unavailable |
| W06 | Windows x64/arm64 | provider account | default provider ready | inventory the private Python and CUA payload; obtain protected runtime adoption authorization only for the post-merge slice | before merge, choose Restart Vadgr and observe progress, then confirm that the profiled unsigned runtime is truthfully unavailable; after merge, run one harmless screenshot task through the authorized bundled CUA | daemon PID/health transition, installed payload inventory and unavailable reason before merge; journal result after protected authorization | restart is truthful; the unsigned profiled runtime refuses launch without an adoption bypass; the held candidate task finishes using pinned CUA 0.7.9 and Python without system Python | private Windows daemon/journal capture | delete test run after filing | one bounded provider call only in the post-merge slice; screen permission | Windows x64 pre-merge slice passed at `24ae14a`: Restart Vadgr changed the daemon PID and returned healthy; the installed payload reported private Python 3.12.14, CUA 0.7.9 and the x64 Windows profile; the unauthorized unsigned managed runtime failed closed. No provider call ran. The authorized real task is post-merge trust work |
| W07 | Windows x64/arm64 | fault-injection snapshot | release-equivalent unsigned installation healthy for the reachable slice; W02 healthy for the held-candidate slices | before merge, retain exact installed identity and use the ordinary unsigned product's reachable update entry; after merge, prepare the held candidate with controlled failure at each downstream phase | before merge, inject or observe download failure; after merge, inject verification, post-verification staging, dependency, daemon-stop, commit and health-check failure one at a time | prior setup launch, binary/version and health after each attempt | every reachable failure is specific and the prior installation remains runnable; no development bypass crosses the signature boundary merely to reach a later fault | private Windows failure matrix | revert injection after each row | no signing retry; held candidate only for downstream slices | Windows x64 pre-merge slice passed at `24ae14a`: the exact unsigned installation reported a specific manifest-download failure while its binary, daemon and health stayed unchanged. Every later phase is unreachable until manifest and Authenticode verification succeed; those controlled faults run post-merge against held bytes and do not block opening or merging the implementation PR |
| W08 | Windows x64/arm64 | none | W07 functional slice complete | corrupt one package-owned file; keep the retained release-equivalent source | choose Repair in Settings | MSI log, repaired hash and successful ordinary launch | repair restores only owned files and preserves owner state | private Windows repair capture | none | administrator only if Windows requests it | Windows x64 pre-merge functional pass at `24ae14a`: Settings-driven Repair restored the deliberately changed owned notice to exact SHA-256 `d70398e81505af04aa4bd17033af9384873ec3d2eaaf4d7a93dcdd7ef0cc4384c`; ordinary relaunch returned to a visible 0.5.0 console and healthy daemon. ARM64 installed-product behavior is unavailable |
| W09 | Windows x64/arm64 | first-release installation; held signed artifact for the trust slice | current artifact healthy | confirm that no verified native predecessor exists and record binary, health and owner-state identity | attempt an unavailable or controlled failed update, then inspect Roll back | specific update failure, unchanged binary/version/health/state, and a truthful no-previous-generation reason; retained-artifact signatures only after merge | failed update preserves the runnable installation and rollback does not invent a generation | private Windows lifecycle capture | keep the fixed test version | no signing call during the pre-merge slice | Windows x64 first-release functional pass at `24ae14a`: the accessible update action reported the specific `release-manifest.json` download failure while the installed binary, daemon and health stayed unchanged; Roll back remained disabled with `No verified previous generation is retained`. Positive update/rollback is owed by the first subsequent native release, not this first installer |
| W10 | Windows x64/arm64 | isolated E2E state only | signed W09 assertions may remain owed; an installed release-equivalent unsigned artifact is sufficient for this functional cell | agent hashes isolated state and records package paths | agent drives uninstall with preservation and reinstall; then selects the separate deletion choice, types `DELETE OWNER DATA` and invokes uninstall | package inventory and isolated-state identity after each operation | first uninstall preserves and reinstall finds state; second separate choice deletes only the isolated Vadgr state | private Windows uninstall capture | reinstall the fixed release-equivalent artifact if later cells require it | agent drives all app controls; protected Windows prompt only if shown | Windows x64 development passed at `eeb06d3`: the first uninstall removed 6,296 package files while preserving the isolated state identity; reinstall found that state and reused exact terms 1.0 acceptance; the separate accessible checkbox plus exact typed confirmation then removed the package and only the isolated Vadgr state. The live run found and fixed the Burn-variable propagation defect before rerun |
| W11 | Windows native x64 and ARM64 | credential-free native producers; exact source and reviewed wheelhouse | corrected source checks are green; no signed artifact is required | assemble both target payloads from the pinned archives in clean staging; retain source, archive and output hashes | move each assembled payload to a different absolute root, remove its assembly root, then run private Python version, payload validation and MCP tools/list before the unchanged fresh-runner observer | exact payload inventory and PE machine headers; ordinary imports, delay imports and export forwarders; independent executable hashes; no assembly path remains | ARM64 base runtime excludes only unreferenced incompatible DLLs; retained native DLL bytes stay unchanged; a required incompatible DLL stops assembly; every retained executable matches the native target; both targets run after relocation; x64 remains unchanged | unsigned preparation artifacts and native job logs; synthetic refusal tests are source evidence only | remove only the isolated job staging after capture | no credentials, signer, provider call or publication | pre-merge pass for x64 and ARM64 at exact source `24ae14a` in producer run `36614929208`: raw and observer jobs passed relocation, architecture, private-Python, payload-validation and MCP tools/list assertions. This does not claim ARM64 installed-product behavior |

## Part M: macOS cells

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions | result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M01 | macOS Intel, then Apple Silicon | clean host; no owner action | no Vadgr app, shim, state or login item; if the release-equivalent unsigned PKG cannot be built, repair or create its credential-free producer on the implementation branch before continuing | agent builds the registered unsigned PKG, records the before inventory and verifies its hash; package signature, notarization and staple run post-merge | agent opens the package through accessibility, inspects terms and invokes decline | before/after `/Applications`, shim, state and background-items inventory | installer makes no mutation | private macOS boundary | delete download after filing | administrator must not be requested before acceptance | partial functional: Apple Silicon unsigned package opened natively, exposed Version 1.0 terms and declined with no mutation at `5df1ad3`; exact final artifact and Intel remain owed. A missing current unsigned PKG is an implementation finding to fix before merge. Signature, notarization and staple are separate post-merge trust assertions |
| M03 | Intel and Apple Silicon macOS | protected signed artifacts | M02 installed | network off after download | run `pkgutil`, `spctl`, `codesign` and stapler checks on package, app, CUA host and nested code | expected Team ID, hardened runtime, timestamp, staple and no `get-task-allow` | every layer verifies offline | private macOS signature report | none | no notarization call | partial: Apple Silicon development package signature, Gatekeeper, app verification, staple and helper requirement were observed at `5302082`; unsigned trust checks rejected the vehicle and the helper had no Team ID or hardened runtime. This was not an offline snapshot. All signed-candidate and Intel assertions remain owed |
| M04 | both macOS architectures | owner | functional restart requires a release-equivalent installation; signed identity continuity requires M02 | record daemon identity; record the helper designated requirement only for the post-merge trust slice | restart app, restart daemon, sign out/in and launch normally | CUA task and process identity after each functional boundary; requirement string and grant continuity after signing | functional restart and login behavior pass before merge; signed helper identity and grants survive all launches in the post-merge trust slice | private macOS identity capture | stay installed | Accessibility and Screen Recording only for the signed identity slice | partial functional: Apple Silicon unsigned public app and daemon restarts remained healthy at `c980421`; exact final functional login rerun and Intel remain owed. Signed requirement and permission continuity are separate post-merge trust assertions |
| M05 | both macOS architectures | owner and provider | M04 functional slice complete | one paired phone | repeat W04 through W06 on macOS | CLI/API/console, device rows, health and journal | same shared behavior; platform launch uses SMAppService agent | private macOS functional capture | remove test run/device | provider billing and phone | partial functional: Apple Silicon machine fields, masked key, exact purge confirmation, CLI/API agreement, restart persistence and bounded CUA screenshot passed at `5302082`; saved-name QR and authenticated Built-in watch ran at `c980421`. The exact-name task rerun succeeded with its journal image inspected. Exact final artifact, Tailscale typed pairing and Intel remain owed; signing is not a prerequisite |
| M06 | both macOS architectures | release-equivalent previous/next packages and isolated E2E state; held signed packages for the MA2 slice | M05 complete | agent captures functional state; capture helper requirement and TCC result only for the post-merge trust slice | agent drives update, repair, rollback, uninstall-preserve, reinstall and the separate explicit purge confirmation; then checks signed identity continuity on held bytes | health and isolated-state identities before merge; signatures, requirement and grant continuity after merge | prior install survives failure; rollback and repair work; MA2 closes across signed update without a new grant | private macOS lifecycle/MA2 capture | agent removes product and test grants after filing | protected administrator or privacy prompt only if shown | partial functional: Apple Silicon unsigned replacement stopped the old daemon and preserved configuration at `c980421`; repair regressions passed at `165b856`. Exact final functional lifecycle, preserve/reinstall/purge and Intel remain owed. Signed grant continuity is a separate post-merge trust assertion |

## Part L: native Linux cells

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions | result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| L01 | native Linux x86_64, then aarch64; X11 and Wayland | clean graphical session; no owner action | no Vadgr XDG generation, command, desktop or autostart entry; if the release-equivalent AppImage cannot be built, repair or create its credential-free producer on the implementation branch before continuing | agent builds the registered AppImage, records the before inventory and verifies its hash; manifest trust runs post-merge | agent opens the AppImage through accessibility, inspects terms and invokes **Decline and close** | before/after XDG data/config, command and state inventories | no product or owner-state mutation | private Linux boundary | remove downloaded files after filing | no root or package-manager action | pre-merge functional assertion: run against the exact release-equivalent AppImage; missing package inputs or payload are implementation findings to fix, while production manifest trust remains owed against the held candidate |
| L03 | x86_64/aarch64, X11/Wayland | clean GUI hosts | L02 installed | keep FUSE; prepare extraction test | verify development integrity metadata before merge and the production attestation bundle after merge; launch normally and with `--appimage-extract-and-run` | target match, size/hash and both launches before merge; certified workflow/runner output after merge | both paths work; every available wrong-root, bundle, workflow, ref, target, size and hash case fails before XDG mutation | private Linux integrity capture | delete tampered copies | none | functional extraction and tamper assertions run before merge; production workflow and attestation assertions remain owed against the held candidate |
| L04 | same matrix | provider and phone | release-equivalent installation healthy; L03 trust may remain owed | one provider/default and paired device | repeat W04 through W06 | CLI/API/console, transport and journal | shared console/backend behavior matches Windows | private Linux functional capture | remove run/device | bounded provider call and phone | pre-merge functional assertion: run against the exact release-equivalent AppImage; no signing identity is required |
| L05 | same matrix | fault-injection host | L04 complete | release-equivalent local previous/next generations; held artifacts for trust assertions | inject every W07 failure; repair, update and roll back | `current` link, version receipts, health and state identity | atomic link restores prior generation; repair uses retained verified source | private Linux lifecycle capture | select fixed generation | no root | functional lifecycle and fault assertions gate merge; retained-artifact trust remains owed against the held candidate |
| L06 | same matrix | isolated E2E state only | L05 functional slice complete | agent records XDG and isolated state roots | agent drives uninstall-preserve/reinstall, then the separate typed purge | exact paths and isolated-state identity | only package/XDG entries removed first; state found on reinstall; purge deletes the exact isolated state root | private Linux uninstall capture | agent removes all test artifacts | no owner action unless a protected package prompt appears | pre-merge functional assertion: run against the exact release-equivalent AppImage; no signing identity is required |

## Part S: WSL cells

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions | result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S01 | WSL x64, then arm64 | clean distribution; no owner action | no Vadgr generation, command or state | agent verifies development integrity metadata and points `RELEASE_DIR` at the release-equivalent local assets; production attestation runs post-merge | agent runs `./install.sh --source "$RELEASE_DIR"`, inspects the terms and enters anything except `ACCEPT 1.0` | before/after Linux roots plus Windows registry and network snapshots | no WSL or Windows mutation | private WSL boundary | remove temporary download directory | no GUI, elevation or Windows permission | pre-merge functional assertion: run against the exact release-equivalent assets; production attestation remains owed against the held candidate |
| S02 | WSL x64/arm64 | clean distributions | S01 complete | local release-equivalent assets in `$RELEASE_DIR`; network blocked | run `install.sh --source "$RELEASE_DIR" --accept-terms 1.0` | verifier output, archive inventory, version/target/pins and health | CLI-only install succeeds with CUA 0.7.9/Python pin and no system Python/toolchain | private WSL install capture | keep installation | no elevation or GUI | pre-merge functional assertion: run against the exact release-equivalent assets; production attestation remains owed against the held candidate |
| S03 | WSL x64/arm64 | none | S02 clean snapshot | tampered copies | before merge, alter verifier, pinned root, target, size, hash, traversal and escaping link; after merge, alter manifest bundle and certified signer/ref/runner | exit and before/after WSL/Windows inventories | every available case fails before install mutation; Windows registry, DNS, firewall, VPN and files unchanged | private WSL negative matrix | delete tampered files | none | functional integrity and filesystem-safety assertions run before merge; production workflow and attestation assertions remain owed against the held candidate |
| S04 | WSL x64/arm64 | provider account | S02 healthy | provider configured securely | run one screenshot task through bundled CUA; compare CLI/API machine config after edits | journal and pin records | task succeeds; machine store persists; no GUI/autostart/service exists | private WSL functional capture | remove run and provider credential | bounded provider call | pre-merge functional assertion: run against the exact release-equivalent assets; no signing identity is required |
| S05 | WSL x64/arm64 | fault-injection distribution | S04 complete | retained release-equivalent previous/next archives; held artifacts for trust assertions | inject failures, update, repair and rollback through `install.sh` | `current`, receipts, health and state identity | prior generation remains runnable and rollback is verified/local | private WSL lifecycle capture | restore fixed version | none | functional lifecycle and fault assertions gate merge; retained-artifact trust remains owed against the held candidate |
| S06 | WSL x64/arm64 | isolated E2E state only | S05 functional slice complete | agent records isolated state identity | agent drives uninstall-preserve/reinstall, then `--delete-owner-state` and types the confirmation | exact Linux roots and Windows no-change snapshot | state survives first cycle; separate purge removes only isolated WSL Vadgr state | private WSL uninstall capture | agent removes test assets | no owner action | pre-merge functional assertion: run against the exact release-equivalent assets; no signing identity is required |

## Part O: shared offline, accessibility and cleanup cells

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions | result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| O1 | every installed target | isolated offline test snapshot | target functional cells pass; signed-only assertions may remain owed | start from a test snapshot whose external network is already unavailable; do not change host firewall, DNS, routing or VPN state | agent launches CLI/console, opens bundled legal notices, restarts, repairs, rolls back and uninstalls | process/health, offline files and package receipts | installed product lifecycle works without repository infrastructure | each private host boundary | discard only the isolated snapshot after evidence is filed | no host network mutation or administrator action | Windows x64 development passed at `eeb06d3`: with the prepared account's external networking already blocked, local install and terms, bundled legal availability, CLI/console launch, repair, two restart-to-one-healthy-daemon checks, truthful unavailable rollback, and accessible uninstall/purge completed. Package and isolated state ended absent; no firewall, DNS, route or VPN setting changed. Other hosts retain their own result |
| O2 | every native GUI target | native accessibility API and screen reader available | GUI installed | agent resets to empty/no-provider and populated states | agent drives all focus, names, roles, loading, empty, failure, destructive confirmation and success states without pointer | AccessKit plus Narrator, VoiceOver or Orca output, app-only capture and backend oracle | complete operation is understandable and actionable; every control works or has a truthful disabled reason | private accessibility capture; no secret entry recorded | agent restores screen reader state | no owner action | Windows x64 pre-merge pass: the Narrator state matrix at `ec66315` remains valid because later changes do not alter control roles or flows; exact-current UIA agrees. At `24ae14a`, isolated OBS `window_capture` using Windows Graphics Capture produced the precise Vadgr-only client while Vadgr was unfocused; visual inspection and backend state agreed, and the private transport-bearing image was withheld. macOS Apple Silicon development at `5302082` verified named native focus, actual VoiceOver speech, secure input, destructive confirmation, minimum window, empty state and daemon failure/recovery. VoiceOver is off. The exact temporary AppleScript-control setting was restored to disabled and persisted after Utility restart on 2026-09-15; no privacy grant changed |
| C1 | each host after all its cells | none | every host cell has terminal result and evidence | agent enumerates Vadgr processes, temporary artifacts, devices, test credentials and isolated test state | agent stops only Vadgr test processes and removes only validated test artifacts, devices and credentials | final process/path/network/device inventory | no test process or artifact remains; source, evidence, configuration, normal owner state and unrelated files remain | private host cleanup record | none beyond this row | no owner action; scope is limited to runbook-created test items | Windows x64 pre-merge cleanup passed at `24ae14a`: the test daemon and console stopped, port 8000 is free, the unsigned test package and isolated state were removed, the held owner state was restored byte-for-byte, phone scratch files were deleted, and Tailscale returned to its initial off state. Standard Cargo cleanup plus validated test-root removal reclaimed 4,568,530,944 bytes. Source, evidence, credentials, owner configuration, unrelated processes and `.tmp-cert-research` remain. macOS partial: September 13 cleanup is historical. Resumed pass console, daemon and isolated broker are now absent; port8000 is free on IPv4/IPv6 and no installed private payload process remains. Original owner API log body is restored. The separate empty-state root is in recoverable Trash and port8011 is free. Main install/state and rebuilt artifact remain preserved for protected continuation; exact phone-created files, final artifact removal, snapshot equality are owed. VoiceOver and its temporary AppleScript-control setting are restored |

## Per-OS results

| Part | Windows native | macOS | native Linux | WSL |
|---|---|---|---|---|
| H: protected owner boundaries | partial functional: F01 QR/Built-in and typed-code/Tailscale completed; W02 is a post-merge trust assertion | partial functional: physical saved-name QR/Built-in pairing completed; M02 is a post-merge signed-identity assertion | blocked before owner action: the current release-equivalent Linux package must be produced on the implementation branch. The VirtualBox host ADB bridge proved one authorized intended physical phone before the owner disconnected it, so phone absence is not the package blocker | Not-Needed: WSL has no native GUI or protected installer prompt |
| W: Windows cells | pre-merge functional qualification complete on available x64 hardware: W01, F01, W03 unsigned, W04, W05, W06 pre-merge, reachable W07, W08, first-release W09, W10, O2 and C1 pass; x64/ARM64 W11 passes. ARM64 installed-product hardware is unavailable. Held-candidate-only slices are tracked separately and do not block merge | Not-Needed: Windows-only cells | Not-Needed: Windows-only cells | Not-Needed: Windows-only cells |
| M: macOS cells | Not-Needed: macOS-only cells | partial functional: Apple Silicon installation, native configuration, phone watch and restart observations are filed; the host must build the exact current release-equivalent unsigned PKG and complete affected lifecycle and cleanup before merge. Intel hardware remains unavailable. Signed identity assertions are tracked separately | Not-Needed: macOS-only cells | Not-Needed: macOS-only cells |
| L: native Linux cells | Not-Needed: native-Linux-only cells | Not-Needed: native-Linux-only cells | blocked before installer execution on the current x86_64 GNOME Wayland VirtualBox host: the credential-free producer has now compiled the pinned native executable and assembled the exact private Python/CUA 0.7.9 payload at `890a7d4`. The reviewed `packaging/inputs/linux-x86_64` packet and registered AppImage remain incomplete. Finish the exact native-library scope, notices and source duties, assemble the package, then run the functional cells. Signing is not the functional blocker. aarch64, X11, bare-metal and unavailable hardware-specific behavior were not run | Not-Needed: native-Linux-only cells |
| S: WSL cells | Not-Needed: WSL-only cells | Not-Needed: WSL-only cells | Not-Needed: WSL-only cells | not run: release-equivalent unsigned WSL assets have not completed functional qualification; signing is not the blocker |
| O: shared offline, accessibility and cleanup cells | pre-merge functional qualification complete on available x64 hardware: prior O1 remains valid; the Narrator state matrix, exact-current UIA, unfocused Windows Graphics Capture and final C1 cleanup pass | partial functional: native focus, VoiceOver speech, state matrix, isolated fixture cleanup and screen-reader-setting restoration ran; exact final offline lifecycle and cleanup remain owed | blocked: no current release-equivalent package or pre-existing isolated offline snapshot is available. C1 remains pending until the Linux cells finish | not run: host functional qualification is incomplete |

## Completion ledger

| host | cells | result |
|---|---:|---|
| Windows x64/arm64 | W01, W02, F01, W03 through W11, O1, O2, C1 | pre-merge functional qualification is complete on available x64 hardware at exact product source `24ae14a`: x64 W01, F01, W03 unsigned, W04, W05, W06 pre-merge, reachable W07, W08, first-release W09, W10, O2 and C1 pass; native x64/ARM64 W11 passes. Prior O1 remains unaffected. ARM64 installed-product behavior is unavailable and recorded honestly. W02 and named held-candidate assertions are post-merge work and do not gate merge |
| macOS Intel/Apple Silicon | M01, M02, F01, M03 through M06, O1, O2, C1 | pre-merge functional qualification is partial: Apple Silicon installed configuration, phone pairing/watch, accessibility and screen-reader restoration observations are filed; the exact current unsigned PKG and affected lifecycle, Tailscale pairing and cleanup remain owed. The host repairs missing unsigned packaging on the implementation branch. Intel hardware remains unavailable. M02 and named signed-identity assertions are post-merge trust work |
| Linux x86_64/aarch64 X11/Wayland | L01, L02, F01, L03 through L06, O1, O2, C1 | blocked on virtualized native Ubuntu 26.04 x86_64 GNOME Wayland: the exact source has no retained AppImage, `native-build-linux-x86_64` artifact, reviewed Linux package-input packet or assembled payload. These are implementation findings the host must repair on the branch before continuing. The host ADB bridge proved the intended physical phone before disconnection, but F01 cannot reach its prepared-QR owner boundary without the package. No isolated offline snapshot exists. aarch64, X11, bare-metal and hardware-specific behavior were not run. C1 remains pending. Signing does not block this lane |
| WSL x64/arm64 | S01 through S06, O1, C1 | pre-merge functional qualification is not run: release-equivalent unsigned assets are required. Production attestation is a separate post-merge trust lane |

Overall functional qualification remains **incomplete** until every applicable
pre-merge assertion has execution evidence and cleanup against exact
release-equivalent unsigned artifacts. CI, source inspection or another host's
result cannot substitute for a functional assertion. Post-merge trust
qualification is separate and does not repeat functional E2E unless the held
packaging changed the behavior being proved.

## Windows qualification history

These observations preserve implementation findings and earlier evidence. They
count only when the completion ledger explicitly establishes that the tested
bytes are release-equivalent and unaffected by later changes. Otherwise rerun
the affected functional assertion against the exact final pre-merge artifact.

| date | exact product subject | affected cells | development observation |
|---|---|---|---|
| 2026-09-02 | `9c7d06970e39c5e9c141205a5b88dd64914497f1` | W04 | Accessibility-driven machine edits agreed with CLI and loopback API reads, survived daemon restart, rejected a read-only field, and restored nullable workspace state. The probe found and fixed omitted-versus-null request handling. |
| 2026-09-02 | `9c7d06970e39c5e9c141205a5b88dd64914497f1` | W06 | Accessibility-driven restart showed the health transition and a new daemon process. A bounded screenshot task completed through an isolated installed-layout payload carrying released CUA 0.7.5. The required candidate rerun still owes CUA 0.7.8. |
| 2026-09-02 | `9c7d06970e39c5e9c141205a5b88dd64914497f1` | O2 | Machine, Providers and Settings exposed named controls through Windows UI Automation; keyboard and Narrator traversal reached all three views; form inputs exposed associated names; unavailable package actions stated why they were disabled. Pairing QR layout remained centered at normal and compact sizes in app-only capture. Empty and daemon-failure states were readable, while destructive and installed-package states remain owed. |
| 2026-09-02 | `9c7d06970e39c5e9c141205a5b88dd64914497f1` | W03 preflight | Locally built x64 release executables with static CRT passed the Windows system-import allowlist. No signature, installer vehicle, clean-host or immutable-candidate assertion ran. |
| 2026-09-02 | `f2a2920a1825bb013434aff37cb2c0f4d8ed71f7` | W01, W10 | Accessibility drove the unsigned development setup through terms decline, install, ordinary console launch and uninstall with owner-state preservation. Decline and uninstall left the expected product inventories, and the package installed 6,185 payload files without system Python. The development-only build intentionally omitted the untrusted rollback-vehicle cache, so no signature, rollback or candidate assertion ran. Finding `WIN-DEV-01`: reinstall requested acceptance of unchanged terms version 1.0 again, contrary to the accepted-once contract. W10 remains owed after custom bootstrapper acceptance-state integration. |
| 2026-09-02 | `f2a2920a1825bb013434aff37cb2c0f4d8ed71f7` | O2 | App-only captures and Windows UI Automation covered installer terms, progress, success, console empty-device state at 1200 by 720, the minimum 900 by 600 window, and uninstall confirmation. Content remained visible without horizontal overflow, installed controls exposed names and actions, and the destructive owner-data choice defaulted off. |
| 2026-09-02 | `d96e4fe40f22e7ebcadc0232fb9ecd13005dc7c9` | W10 | Fixed `WIN-DEV-01`. A native bootstrapper extension accepted only a preserved record matching the exact compiled terms version and SHA-256. Reinstall labeled version 1.0 as accepted previously, disabled repeat assent, kept Install enabled, and made no mutation before the accessibility-driven Install action. Setup completed and Open Vadgr launched the installed console. This unsigned development run does not prove candidate signatures, rollback or the complete W10 cell. |
| 2026-09-02 | `97f69ae2a2437bafacf4dfde2e6a598397e8e3f5` | O2 | Fixed the modal trap found while preparing physical pairing. The scrim now stays below the dialog, and outside click, Cancel pairing and Escape share one dismissal path. Each path was driven against the installed x64 console through Windows UI Automation and restored Machine, Providers and Settings as enabled. Pairing dismissal also closed the daemon pairing window, while API-key dismissal clears the secret field. The installed executable hash matched the corrected release build. |
| 2026-09-02 | `97f69ae2a2437bafacf4dfde2e6a598397e8e3f5` | O2 | The pinned WixStdBA installer exposed Install, Decline, Repair, Uninstall and Close as native Windows buttons with keyboard tab stops. A COM UIA probe reported their Button roles and Invoke support and invoked maintenance Close without focus. The PowerShell `System.Windows.Automation` wrapper collapsed both these controls and a stock MessageBox to patternless panes on this host, so that wrapper result is not treated as a product accessibility defect. |
| 2026-09-14 | `ec66315d80c3dea5934e3e94b433ffbba79098bd` | F01, W05 | A physical Android phone paired through the agent-prepared QR/Built-in flow after the owner only aimed the camera. Windows UI Automation, ADB and the loopback APIs agreed on the resulting device and Built-in availability. The first typed-code attempt truthfully failed because existing inbound rules block the installed path. Without mutating them, the exact product source was rebuilt at an already-allowed path; phone TCP reachability then passed, typed-code pairing completed over Tailscale, and mobile also named Built-in as available. The agent repeated cancel/confirm revoke and restored one typed pairing. The 900 by 600 console wrapped diagnostics without horizontal overflow. No secret or signed-candidate assertion was retained. |
| 2026-09-14 | `ec66315d80c3dea5934e3e94b433ffbba79098bd` | O2 | Narrator remained active while UI Automation plus keyboard input drove Machine, Providers, Settings, restart progress/recovery and the destructive uninstall dialog. The installed package exposed correct names, roles, enabled states and reasons. Owner-data deletion defaulted off; a wrong phrase kept Uninstall disabled; the exact phrase enabled it; Keep installed dismissed without mutation. Earlier evidence at this product line supplies the empty and daemon-failure states. Narrator was stopped and the installed daemon remained healthy. |
| 2026-09-14 | `ec66315d80c3dea5934e3e94b433ffbba79098bd` | W10, O1 | Neither assertion depends on signing, so their isolation blocker was investigated directly. Two prepared E2E accounts and account-scoped offline rules exist, but neither account has a profile or interactive token and the current process has no credential for it. Windows Sandbox, Hyper-V tooling and an existing VM are absent. The remaining purge/offline actions require a protected interactive logon; owner state and host-network mutation were not used as substitutes. |
| 2026-09-14 | `eeb06d3595b06efb47b20d0561f3d616ec431abd` | W10 | The isolated preserve/reinstall cycle passed, then the first explicit purge exposed `WIN-DEV-02`: Burn rejected the non-overridable `PurgeOwnerData` command-line input, so the confirmed console action could not delete owner state. The bundle now declares that hidden numeric variable command-line overridable, the backend emits WiX's documented `Variable=Value` form, and unit plus packaging regressions cover both layers. A rebuilt unsigned package then removed only the isolated package and Vadgr state through the accessible checked and typed console flow. |
| 2026-09-14 | `eeb06d3595b06efb47b20d0561f3d616ec431abd` | O1 | A separate prepared account with external networking already unavailable completed local install, installed legal access, CLI/console launch, repair, restart and health, truthful unavailable rollback, and uninstall/purge. Process probes observed exactly one healthy daemon after start and restart. The account finished with no Vadgr package or state, and the host firewall, DNS, routing and VPN were not changed. |
| 2026-09-23 | `d9d9b23cc992305e50060e50d01c18d241b17498` | W01, W03 unsigned slice, W06 through W08, W10 preserve slice, O2 | A native Windows x64 WiX 7 development setup exposed readable Version 1.0 terms, reused exact prior acceptance, declined without package or owner-state mutation, installed with truthful progress, launched normally, carried private Python 3.12.14 and CUA 0.7.8, restarted to one healthy daemon, and completed one bounded screenshot task through Gemini 3.6 Flash. App-only `PrintWindow(PW_CLIENTONLY)` captures worked while another application had focus. Repair restored an intentionally changed owned file to its exact prior hash. Uninstall preserved the complete owner-state identity, and reinstall found that state. Finding `WIN-DEV-03`: the predecessor's update check panicked by starting a Tokio runtime inside the CLI runtime. The corrected setup `2777d8a213fd81bf7ec00e49e852cab3c27b0ec74ff7c970cdefaa26bdda6957` and MSI `f374bf76aac36a42018f583ecc62307ecfff532b7d06070ed280c4708ebbac6c` returned one specific manifest-download failure without a panic while the installed binary and healthy daemon remained unchanged. Tests now call the synchronous network path from an existing async runtime. Owner state was restored to its exact pre-pass aggregate. These unsigned observations do not satisfy Authenticode, publisher, immutable-candidate, arm64 or release assertions. |
| 2026-09-29 | `24ae14a8c585a555f14fe1186f4986120b32a00e` | W01, W03 unsigned slice, W04 carry-forward, W06 pre-merge slice, reachable W07, W08, W09 first-release slice, W10 carry-forward, W11, O2 | Exact final x64 setup `3299a2a9498236b874a4385d8085e7f521fe6cc760aec4f0c98e1dd083c98d97` declined with zero mutation, installed with truthful progress and success, launched healthy, restarted to a new healthy daemon, inventoried private Python 3.12.14 and CUA 0.7.9, and correctly refused unauthorized profiled-runtime launch. Failed update preserved the installed binary and health; rollback truthfully named the absent predecessor. Settings-driven Repair restored an owned file exactly. Producer run `36614929208` passed native x64 and ARM64 relocation, architecture, payload-validation and MCP observer checks. The decline modal exposed a harness omission: native owned dialogs were absent from UIA's top-level listing; native handle enumeration now drives their accessible controls. The OpenGL console returned a blank `PrintWindow` client, so no desktop crop was substituted: an isolated OBS `window_capture` source using Windows Graphics Capture produced the exact Vadgr-only client while another window held foreground, and visual inspection plus UIA/backend oracles agreed. That private transport-bearing image was withheld. No signing or provider call ran. |

## Linux qualification history

These observations preserve implementation findings and earlier evidence. They
count only when the completion ledger explicitly establishes that the tested
bytes are release-equivalent and unaffected by later changes. Otherwise rerun
the affected functional assertion against the exact final pre-merge artifact.

| date | exact product subject | affected cells | development observation |
|---|---|---|---|
| 2026-09-13 | `206a30653c6454d1ebfc7ecb6e60800cf3aa1f8b` | L01, L03 | Fixed the native AppImage build after the desktop entry named an icon that the AppDir did not contain. The packaging regression failed against the handoff and passed after the SVG was installed under the declared desktop icon name. |
| 2026-09-13 | `730bed8385139a55670bdd8dadb2d2cef800afae` | L01, L03 | An unsigned x86_64 Wayland development AppImage passed external disposable-key verification, normal FUSE launch, extraction launch, accessibility-driven terms decline, and the wrong key, signature, target, size, hash, tampered-artifact, missing-manifest and missing-signature rejection matrix without product-state mutation. Official signing, the immutable candidate, aarch64 and X11 remain owed. |
| 2026-09-14 | `730bed8385139a55670bdd8dadb2d2cef800afae` | L04, O2 | CLI and loopback API machine reads agreed after name, role, autonomy and workspace edits; the values survived restart, a read-only field was rejected, a no-op was idempotent, and original values were restored. Gemini connected from the protected environment, became the ready default, and completed one read-only screenshot task through the installed CUA 0.7.8 payload in two iterations. AT-SPI exposed the populated provider state and restarted the daemon to a new PID without losing that default. The pinned Linux adapter exposes entries without EditableText, and host Wayland rejected AT-SPI keyboard synthesis, so console text entry and the typed purge remain owed. Orca also hit its host-service watchdog, and app-only pixel capture was unavailable under the protected Wayland capture boundary. Phone and paired-device assertions remain owed. |
| 2026-09-13 | `730bed8385139a55670bdd8dadb2d2cef800afae` | L05 | Fixed Repair falsely reporting failure after it restored a corrupted owned AppImage while the daemon was already healthy. The regression failed before the health fallback and passed after it. A rebuilt development AppImage then restored the exact expected hash, kept health available and showed no repair error. Signed update, rollback and the remaining distinct-generation fault matrix remain owed. |
| 2026-09-13 | `730bed8385139a55670bdd8dadb2d2cef800afae` | L06, C1 | Accessibility drove uninstall with state preservation and reinstall, and the preserved state was found. The separate purge dialog defaulted off and required the exact typed phrase, but the adapter and Wayland text-input boundary prevented autonomous entry. Test windows and Orca were stopped and the original accessibility settings were restored. The fixed development installation, healthy daemon and isolated owner state remain intentionally installed for the attended phone continuation. |
| 2026-09-24 | `d4dd7b000fa82095ebb7a98a84ed7b2d5202a7c6` | L01 through L06, F01, O1, O2, C1 | The native continuation stopped before product startup. No held candidate workflow run exists. The exact source has no `packaging/inputs/` tree or assembled private CUA payload, and the Linux build refused the missing payload with exit 2. ADB listed no phone and the host has no pre-existing isolated offline snapshot. Rust tests, Clippy, formatting, 888 Python tests, secret checks, runbook arithmetic and style passed. No source binary, earlier package or synthetic legal input was substituted for the missing current artifact. Private evidence: PR #176, `20260924-linux-x86_64-wayland-continuation`. |
| 2026-09-29 | `24ae14a8c585a555f14fe1186f4986120b32a00e` | L01 through L06, F01, O1, O2, C1 | On an Ubuntu 26.04 x86_64 GNOME Wayland VirtualBox guest, no retained or local release-equivalent AppImage exists. GitHub reports no `native-build-linux-x86_64` artifact, and the exact source lacks `packaging/inputs/linux-x86_64` plus an assembled payload. No synthetic review input or earlier package was substituted. The earlier phone diagnosis was corrected: after stopping guest-local ADB, `ADB_SERVER_SOCKET` through the VirtualBox host gateway found exactly one authorized intended physical phone before disconnection. This proves the bridge only; F01 remains blocked before its QR boundary by the package. No pre-existing offline snapshot exists, and C1 remains pending. Private evidence: PR #176, `20260929-linux-x86_64-virtualbox-continuation`. |

The 2026-09-30 Linux continuation added a credential-free preparation producer.
At exact source `890a7d465c426ab1f88475e62edbd3f0052f63f8`, the pinned Rust
1.97.1 native build completed, 57 private runtime binaries passed architecture
verification, and relocated private Python 3.12.14 imported CUA 0.7.9. These are
package-preparation observations, not installed-product passes. The Linux
package-input review and assembled AppImage remain incomplete. The full Python
producer archive matched all 4533 install-only members; its 1667 additional
members are not claimed as shipped. Native-library notices and source duties
still need exact payload review. Existing failed attempts remain in private
evidence PR #176 under `20260930-linux-x86_64-package-preparation`. No production
signing prerequisite blocks this implementation work.

The local preparation executable required GLIBC 2.43 and is not the registered
Ubuntu 24.04 package subject. Source
`73fa58ccd1989e58f7467bc2f2abe2286aaeb72f` adds credential-free Ubuntu 24.04
preparation and a packaging guard for the registered GLIBC 2.39 baseline.
Successful workflow run `36726433875` retained artifact `11103702051`.
Independent inspection matched all 6307 preparation members, including modes
and links. Its native executable is 65465120 bytes, SHA-256
`a4f1b6c8a81eb74268c25ded72c18938e821d00233f1203369a73409e3ef8af3`,
with maximum required GLIBC 2.39. The retained preparation is not an AppImage.
Reviewed Linux notices and source delivery still precede assembly and the
installed-product cells. CI success is not a functional cell pass.

### Current Linux disposition after packaging repair

The exact repaired product source is
`229c665d429e64ebc2501c59b3f38d883a8e774b`. Native Ubuntu 24.04 workflow
`36736024658` retained development preparation artifact `11107323673`.
Independent verification matched all 5826 receipt members, modes and links.
Its executable is 65442928 bytes, SHA-256
`2bca1d2507548d53c5d160be91ba89c9fda184f10336a1bd195c3327a04c2495`.
The preparation tar is 152280148 bytes, SHA-256
`dc2ff5d5fe9cdb819c2133a878057aff60f01e3eac175340d94cbdf186935d9e`.
Neither file is the registered AppImage or an installed-product pass.

The retained private runtime reports Python 3.12.14 and CUA 0.7.9. The Linux
bootstrap repair removes pip and ensurepip, including nested foreign launchers.
Regressions failed before both pruning and the assembly-reuse guard, then
passed with the repairs. The new preparation contains no bootstrap files and
its executable requires at most GLIBC 2.39. Fresh Linux and WSL payloads are
required. Windows and macOS behavior is unchanged by this Linux-only pruning.

The Linux-specific inventory, SBOM, notices and source-delivery draft is now
complete. It contains 825 component records and 5285 files. Two independent
offline source rebuilds passed on Ubuntu 26.04, including a modified Plasma
description reaching rebuilt compiler metadata. Those builds prove source
rebuild capability, not reproduction of Ubuntu 24.04 artifact bytes. Full
CPython and Alpine runtime producer rebuilds are not claimed.

The exact packet still requires publisher-owner approval. Its manifest SHA-256
is `b2e1d2b29e88bca626e973bfc8234305945280331cdfad6e43342a3b64874c41`.
Existing Version 1.0 terms are unchanged. This is not a signing or new-counsel
prerequisite. The package validator rejected the unapproved draft. No approval
flag was fabricated, and no earlier artifact was substituted.

The following current results supersede earlier Linux observations for this
source. The host is Ubuntu 26.04 x86_64 GNOME Wayland inside VirtualBox:

- L01 and L02: blocked before installer execution by exact Linux packet
  approval. The registered AppImage must then be assembled and tested. A
  protected dependency prompt has not been reached.
- L03: functional integrity and both launch paths remain blocked by the same
  package prerequisite. Production attestation is separately owed post-merge.
- L04: unattended machine, restart and runtime-task assertions remain blocked
  by the package. Device assertions additionally require the physical phone.
- L05 and L06: blocked before installed lifecycle, preservation and explicit
  purge assertions by the package prerequisite. No owner data was changed.
- F01: blocked by the package and the unavailable physical phone. The owner is
  away with the phone. No scan or ordinary phone action is requested now.
- O1: not run because no pre-existing isolated offline snapshot is available.
  Host firewall, DNS, routes, proxy, VPN and services remain unchanged.
- O2: blocked before installed accessibility and exact unfocused capture by
  the package prerequisite. AT-SPI and WINDOW portal availability are setup
  observations only, not a visual or accessibility pass.
- C1: partial preparation cleanup only. Preserve the exact review packet and
  preparation for continuation; final installed-product cleanup remains owed.

aarch64, X11 and bare-metal hardware-specific behavior were not run because
this host supplies none of those variants. Full Rust tests, Clippy, formatting,
1426 Python tests, secret checks and E2E gates passed for the repaired source.
All required implementation checks completed successfully. No installed-product
Linux cell inherits those source or CI results. Nothing was merged, signed,
tagged, published or released.

## macOS qualification history

These observations preserve implementation findings and earlier evidence. They
count only when the completion ledger explicitly establishes that the tested
bytes are release-equivalent and unaffected by later changes. They never satisfy
a post-merge signed-identity assertion, unavailable architecture, owner action
or phone action.

| date | exact product subject | affected cells | development observation |
|---|---|---|---|
| 2026-09-13 | `936cce15cd0d9162d2a689346352a414989fb954` | candidate assembly | Fixed two candidate workflow failures. macOS now assembles the payload beside the temporary responsible host. Linux, WSL and macOS invoke their non-executable package sources through `sh`. Both regression tests failed before the fixes and passed after them. |
| 2026-09-13 | `5df1ad3b9ef96ebb9f7bf0732d06fa01750d5a53` | M01 | Fixed the false Rosetta requirement on the arm64 package by generating exact target host architecture metadata. The regression test failed before the fix. The rebuilt unsigned package opened natively, showed the Version 1.0 terms, accepted the accessibility-driven Disagree action and left every product path and receipt absent. Final legal, signature, notarization, immutable and Intel assertions remain owed. |
| 2026-09-13 | `5df1ad3b9ef96ebb9f7bf0732d06fa01750d5a53` | M03 | The arm64 development package reported no package signature, no usable Gatekeeper signature and no staple. The helper was arm64 with bundle identifier `com.montbrain.vadgr.cua`, but it had only a linker ad hoc signature and no Team ID. This is the expected unsigned state, not a signature pass. |
| 2026-09-13 | `5df1ad3b9ef96ebb9f7bf0732d06fa01750d5a53` | O2 | macOS accessibility exposed named Installer controls for the terms and decline path. The installed console state matrix remains owed because accepting the legal terms and the protected installation prompt require the owner. |
| 2026-09-15 | `bdb353cce901e6a313698686d700089cdc79e20e` | M01, F01 setup | Finding `MAC-DEV-04`: two owner-authorized unsigned installations failed while Installer launched preinstall. Both archived installer scripts retained non-executable mode 0644. Direct launch independently failed with PermissionError before execution. No app or package receipt was installed. The regression failed before executable staging and passed afterward; installation and the physical QR cell remain owed against the rebuilt repair. The package assembly change affects macOS only and requires new macOS artifact observations. |
| 2026-09-15 | `62c247c7d8d58cd5cce2033b68a4b2df21a6fc00` | M01, F01 setup | Executable script staging closed the preinstall launch failure in the rebuilt unsigned package. Finding `MAC-DEV-05`: postinstall then created the shared Vadgr state parent as root while changing ownership only of package-cache. The owner daemon could not create state and stopped before health; an independent owner write reproduced Permission denied. Installer rolled the app back and left no package receipt. Owner-scoped cache creation and copying passed a regression that failed without the repair. The next rebuilt installation remains owed. |
| 2026-09-15 | `4d6502d16471dec7fb4d32648bd045b78ba0bae1` | M01, M06 regression | Rollback inspection found that failure after daemon startup could remove the app without stopping the new process. Two regressions failed without transaction-owned process tracking. The repair verifies the new PID, owner, serve command and start identity before signalling, waits for exit, and preserves app and backup on an identity or shutdown failure. Twelve packaging tests passed, including prior, malformed, foreign, changed, exited and stuck process cases. These are regression results, not live lifecycle verdicts; a rebuilt installed rerun remains owed. |
| 2026-09-15 | `0a57100e8588593d25b6e7c3182808068a6b2666` | M01, F01, M04, M06 regression | Public unsigned Installer completed, the installed console opened, the owner state parent was writable, and the daemon reported healthy with bundled CUA 0.7.8. Native Accessibility connected Gemini, selected Flash-Lite and saved a test machine name. Physical Built-in QR pairing succeeded; cancel kept its device and confirm removed it. Typed-code pairing could not reach the tailnet: the phone had no active VPN transport and direct TCP probes also failed. No network setting was changed. Finding `MAC-DEV-06`: QR and claim responses used the hostname instead of the saved name; two route regressions failed before reading the machine store. Lifecycle inspection also found that replacing the app while its previous daemon remained alive blocked repair startup; two packaging regressions failed before ownership-verified prior-process shutdown. Both repairs require rebuilt live reruns. The shared naming repair touches every OS's pairing-name assertions; earlier development observations remain historical, not coverage of the new behavior. |
| 2026-09-15 | `c980421d4a8a7e7327ea97406764fbe40f96c0fe` | M01, F01, M04, M05, M06 development | Rebuilt public Installer replacement stopped the recorded prior daemon and launched the installed candidate with preserved settings. A fresh physical Built-in QR claim displayed the saved test name, closing MAC-DEV-06 in development. Watching a synthetic held run produced connected true on the authenticated device API; Keep paired preserved the row, and public cancellation followed by reopening the phone conversation disposed the watch connection. Public daemon restart produced a new PID and preserved machine fields, terms, provider default and pairing. CLI and API rejected a read-only version edit, and a same-value edit preserved the machine snapshot. Signed identity, permission-retention, login, Intel and successful Tailscale typed pairing assertions remain owed. |
| 2026-09-15 | `c980421d4a8a7e7327ea97406764fbe40f96c0fe` | M05, O2 finding | Finding MAC-DEV-07: native AXValue assignment reported success on the named Machine name field, but the draft, Save changes and API retained its old value. The pinned macOS accessibility adapter emits SetValue while the pinned egui text widget does not handle it. A permanent console-owned text control handles that native action for machine name, workspace, role prompt, masked provider key and explicit purge confirmation. All five new regressions failed with the handler disabled and passed with it; installed rebuilt native-input reruns remain owed. The native action handler is macOS-only. |
| 2026-09-15 | `c980421d4a8a7e7327ea97406764fbe40f96c0fe` | M05 development | With the installed public CLI and isolated child HOME, browser broker and discovery path, bundled CUA completed a read-only cropped screenshot task in two iterations. Its journal records exactly one successful screenshot_region call returning image content from inside the controlled Providers window. This is unsigned functional coverage only, not a stable permission identity or normal-login grant pass. Native Repair rejected the unsigned package but displayed only a generic lifecycle exit status; a regression reproduced the missing trust reason. The macOS-only repair exposes only exact allowlisted product errors, bounded to a small stderr prefix, and suppresses arbitrary diagnostics. Its installed rebuilt Repair and Roll back reruns remain owed. |
| 2026-09-15 | `ed64e2336babbc44d22a3e750463b668549f53b2` | M01, M05, M06, C1 package closure | Finding MAC-DEV-09: preserved development archives retain an absolute private-interpreter link to their assembly origin. A fresh cold-copy regression failed with the origin absent before the repair. New Unix assembly uses an owned relative interpreter link and removes obsolete build-home metadata after dependency sync; a new recipe generation preserves the legacy environment. Runtime discovery rejects an escaping interpreter. The repaired cold-copy regression reported Python 3.12.14, CUA 0.7.8 and only local paths. These are regression observations, not installed-product E2E. Mac install, CUA, lifecycle and cleanup require rebuilt reruns; shared Unix changes also require native Linux and WSL cold install and lifecycle reruns. Windows launcher metadata is unchanged. Signed qualification remains owed. |
| 2026-09-15 | `cf03befa66c89892411541e9e9b576dcf1a492d5` | macOS candidate legal/signing boundary; M01 through M06, O2, C1 artifact reruns | Finding MAC-DEV-10: an unreviewed synthetic archive reached every mocked native signing step under the old signer. No production credential or native signing tool was used. The repaired workflow checks both target input sets, assembly checks its actual payload, and the signer checks extracted legal/SBOM/offline bytes against the exact source inventory and review before codesign. Source-only results, drafts, changed or substituted files and incomplete review are rejected. The draft generator cannot approve inputs. Regression results are not signed E2E: actual legal review, the offline release identity, protected candidate artifacts and all affected installed macOS reruns remain owed. Existing Linux, WSL and Windows builders do not consume this new macOS input path. |
