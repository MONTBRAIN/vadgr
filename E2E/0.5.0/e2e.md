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

The Linux development producer compiles the explicit, default-off
`linux-unsigned-qualification` feature. Its installer must show
`Unsigned development build. Not for release.` before assent. Verify the
retained `.development.json` beside the exact vehicle, including its source
commit, source tree, architecture, inventory and vehicle digest. The installer
binds these values to its compiled identity. No runtime flag, environment
variable or missing signature may enable this mode in a production binary.
Development repair uses the retained exact receipt and vehicle. Development
generations cannot mix with signed generations or assert a production release
sequence. This first release has no verified predecessor; do not synthesize
another development source to claim successful cross-generation rollback.
The trusted producer and promotion checks must reject development and
unclassified Linux bytes even when their sidecar is omitted. This mechanism
does not satisfy any post-merge publisher, signing, attestation or adoption
assertion. Rerun the installed functional assertions after rebuilding; source
tests alone do not close the failed installer observation.

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

### Native desktop cold-start checklist

Read the docs engineering section "Native desktop cold-start procedure" before
GUI cells. A supported Ubuntu VirtualBox guest is virtualized native coverage;
record the actual guest, virtual hardware, architecture, desktop and protocol.
It is not bare-metal, another architecture or another desktop-session pass.

For Linux, read `harness/linux_atspi.py` and
`harness/linux_portal_capture.py` before using them. The driver needs system
Python GI with Atspi; capture also needs Gio, Gst and the `pipewiresrc`,
`videoconvert`, `pngenc` and `appsink` elements. These are test-driver
dependencies, not dependencies of the installed Vadgr package.

1. Record the original desktop accessibility, screen-reader and session AT-SPI
   settings, including unset values. Enable only what this session needs and
   restore the exact prior state later. Record every assistive process started.
2. Launch the exact retained package outside its checkout and record its PID.
   Poll bounded readiness. Use
   `/usr/bin/python3 E2E/0.5.0/harness/linux_atspi.py tree --pid <pid>` with repeated
   `--tree-allow-name <safe-label>` flags before saving a tree. Redact private
   titles and values at acquisition; never capture a secret to prove a field.
3. From that fresh tree, select one exact name and role. Use the helper's
   `act --pid <pid> --name <name> --role <role> --action <observed-action>`.
   Reacquire the tree and inspect the independent machine result. Native action
   acceptance is not proof of mutation, and disabled semantics need their own
   negative check even when the product guard rejects activation.
4. On an isolated ordinary field, use `set-text` with its exact PID, name, role
   and `--value-stdin`. Prove readback and save before relying on settings or
   typed purge. `editable=true` does not prove `EditableText.SetTextContents`.
   Preserve native refusal as a finding; do not inject keys, use clipboard,
   edit the database or ask the owner to type instead.
5. Invoke `/usr/bin/python3 E2E/0.5.0/harness/linux_portal_capture.py` with
   `--output <new-private.png> --delay 15 --timeout 120`. Inspect the chooser's
   fresh AT-SPI tree, select only the intended WINDOW and invoke its enabled
   Share action. Move focus to
   another safe application during the delay through native accessibility.
   Inspect the resulting exact application image and record focus separately.
6. If the window row has no action and native Selection refuses it, retain the
   failed probe and cancel the owned chooser. This alone does not prove a
   protected owner prompt. Do not retry indefinitely or substitute a desktop
   capture, crop, focused image or tree. Leave the exact visual assertion owed
   and continue independent functional cells.
7. After reboot, reacquire process and session identities. Preserve interrupted
   attempts without guessing exit codes. At cleanup restore assistive settings
   and stop only pass-created processes and capture sessions.

### Desktop visual acceptance

Visual inspection is mandatory and separate from accessibility and backend
checks. Open each exact application-only capture at its intended reading size
and compare it with the approved mockup. Record the tested artifact digest,
capture digest, host/session, window size, display scale, theme and observation.
A screenshot file, correct UI tree, successful API call or owner screen report
alone does not establish a visual pass.

For W01, M01 and L01, inspect the terms before acceptance. Headings, paragraphs,
emphasis and lists must render as readable document content, without unintended
Markdown markers such as `###` and `**`. Preserve the approved source text,
terms version and acceptance hash; rendering is not a legal-content revision.
Inspect unchecked acceptance, visibly disabled installation and the decline
path. Repeat the relevant installation cell for its progress, failure and
success states, including L02's available ordinary-install slice.

For W04 through W10, M04 through M06, L04 through L06, F01 and O2, inspect every
applicable console and dialog state: empty, populated, loading, failed,
disabled, focused, destructive confirmation and success. Check readability,
wrapping, scrolling, clipping, contrast, alignment, spacing, missing glyphs and
control reachability at default and minimum supported window sizes, supported
display scales and both supported themes. Visible states must agree with the
fresh accessibility tree and independent machine oracle. Use isolated safe data;
never retain secret-bearing captures.

Repeat affected visual checks after a rendering fix and rebuilt artifact.
If the required native capture fails, preserve the probe and leave the exact
visual assertion owed. Continue independent functional assertions, but do not
claim complete GUI qualification or substitute an owner inspection, desktop
capture, crop or focused-only image.

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
| L02 | native Linux x86_64/aarch64, X11 and Wayland | owner can approve a package-manager prompt if it appears | release-equivalent AppImage is ready and FUSE dependency is absent | drive install until the protected package prompt appears | Verify the prompt names only the documented FUSE dependency, then approve it. Do nothing if no prompt appears. | installer resumes its visible phases | private Linux boundary | keep installation | separate package-manager approval | partial functional at `eab017e5` on virtualized x86_64 GNOME Wayland: ordinary install, installed health, Open Vadgr and unfocused installer Close completed on a FUSE-equipped host. No package-manager prompt appeared. Missing-FUSE approval and exact visual assertions remain owed |

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
| L01 | native Linux x86_64, then aarch64; X11 and Wayland | clean graphical session; no owner action | no Vadgr XDG generation, command, desktop or autostart entry; if the release-equivalent AppImage cannot be built, repair or create its credential-free producer on the implementation branch before continuing | agent builds the registered AppImage, records the before inventory and verifies its hash; manifest trust runs post-merge | agent opens the AppImage through accessibility, inspects terms and invokes **Decline and close** | before/after XDG data/config, command and state inventories | no product or owner-state mutation | private Linux boundary | remove downloaded files after filing | no root or package-manager action | partial functional at exact `eab017e5`: unchecked assent kept Install disabled; native Decline exited and preserved the complete scoped product inventory. Rendered-terms inspection remains owed because WINDOW-only portal capture produced no exact app-only image |
| L03 | x86_64/aarch64, X11/Wayland | clean GUI hosts | L02 installed | keep FUSE; prepare extraction test | verify development integrity metadata before merge and the production attestation bundle after merge; launch normally and with `--appimage-extract-and-run` | target match, size/hash and both launches before merge; certified workflow/runner output after merge | both paths work; every available wrong-root, bundle, workflow, ref, target, size and hash case fails before XDG mutation | private Linux integrity capture | delete tampered copies | none | unsigned functional slices passed at exact `eab017e5`: twelve development-integrity negatives rejected without scoped mutation; ordinary and extraction launches reached terms, and extraction Decline preserved the product inventory. The runtime left its confined extraction output. Production workflow, attestation and immutable trust assertions remain owed; aarch64 and X11 remain not run |
| L04 | same matrix | provider and phone | release-equivalent installation healthy; L03 trust may remain owed | one provider/default and paired device | repeat W04 through W06 | CLI/API/console, transport and journal | shared console/backend behavior matches Windows | private Linux functional capture | remove run/device | bounded provider call and phone | partial functional at exact `eab017e5`: native edits and cancellation, CLI/API equality, read-only rejection, no-op identity and restart persistence passed. Native masked provider connection, default selection, catalog refresh and disconnect cancellation agreed with independent reads. Native Pair device and Cancel pairing closed the pairing window without adding a device or changing the default. Private Python reported 3.12.14 and CUA metadata 0.7.9; computer use remained unavailable. No managed-runtime admission or CUA task is claimed. Phone and exact visual assertions remain owed |
| L05 | same matrix | fault-injection host | L04 independent functional assertions complete; phone observations remain separately owed | retain the exact current unsigned installation; use the ordinary configured or explicit update source; require a verified predecessor only when one exists | before merge, exercise reachable update-source failure and preservation, repair, and the first-release unavailable-rollback reason; after merge, inject the downstream W07 trust-gated failures; exercise positive update/rollback at the first subsequent native release | `current` link, exact binary and receipt, health and owner-state identity after each attempt | reachable failure is specific and preserves the runnable generation; repair restores package-owned bytes; no predecessor is invented; downstream phases retain their ordinary verification gates | private Linux lifecycle capture | select fixed generation | no root, network mutation or development trust bypass | partial functional at exact `eab017e5`: installed public CLI and Settings reached manifest-download failure and preserved the runnable generation and selected machine state; native Repair restored deliberately altered package bytes exactly. Unsigned apply refused, and rollback stated that no verified predecessor exists. Positive update/rollback and downstream trust-gated faults remain owed against an eligible subject |
| L06 | same matrix | isolated E2E state only | L05 functional slice complete | agent records XDG and isolated state roots | agent drives uninstall-preserve/reinstall, then the separate typed purge | exact paths and isolated-state identity | only package/XDG entries removed first; state found on reinstall; purge deletes the exact isolated state root | private Linux uninstall capture | agent removes all test artifacts | no owner action unless a protected package prompt appears | functional observations at exact `eab017e5`: cancellation preserved the installation; uninstall-preserve retained identical state-file hashes; retained-assent reinstall recovered the selected CLI/API state; empty and wrong purge phrases stayed disabled, while exact native confirmation removed the isolated package and Vadgr state. Exact visual assertions and final C1 remain owed |

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
| H: protected owner boundaries | partial functional: F01 QR/Built-in and typed-code/Tailscale completed; W02 is a post-merge trust assertion | partial functional: physical saved-name QR/Built-in pairing completed; M02 is a post-merge signed-identity assertion | partial functional: exact `eab017e5` installed without a package-manager prompt on the available FUSE host. The missing-FUSE variant was not exercised. F01 remains owed: the current host ADB server probe returned connection refused before listing a phone. The provider/default setup is preserved; no scanner-ready claim is made | Not-Needed: WSL has no native GUI or protected installer prompt |
| W: Windows cells | historical pre-merge functional qualification completed at `24ae14a` on available x64 hardware; shared update changes and the `bb8fb0a8` console action/refresh fix require affected update, restart/action and O2 reruns against a rebuilt package. Unchanged observations remain filed; W11 producer coverage is not ARM64 installed-product coverage. ARM64 installed-product hardware is unavailable. Held-candidate-only slices remain separate | Not-Needed: Windows-only cells | Not-Needed: Windows-only cells | Not-Needed: Windows-only cells |
| M: macOS cells | Not-Needed: macOS-only cells | partial functional: Apple Silicon installation, native configuration, phone watch and restart observations are filed; the host must build the exact current release-equivalent unsigned PKG and complete affected lifecycle and cleanup before merge. Intel hardware remains unavailable. Signed identity assertions are tracked separately | Not-Needed: macOS-only cells | Not-Needed: macOS-only cells |
| L: native Linux cells | Not-Needed: native-Linux-only cells | Not-Needed: native-Linux-only cells | partial functional at exact `eab017e5` on Ubuntu 26.04 x86_64 GNOME Wayland VirtualBox: normal/extraction decline, twelve integrity rejections, installed health, unfocused Close, native/CLI machine edits, API equality, restart persistence, private Python execution, public update failure, repair and preserve/reinstall/purge observations passed. The provider continuation also verified masked connection, default selection, refresh and cancellation. These are assertion-level observations, not whole L01 through L06 passes. Exact visuals and phone work remain owed. aarch64, X11 and bare-metal behavior remain not run | Not-Needed: native-Linux-only cells |
| S: WSL cells | Not-Needed: WSL-only cells | Not-Needed: WSL-only cells | Not-Needed: WSL-only cells | not run: release-equivalent unsigned WSL assets have not completed functional qualification; signing is not the blocker |
| O: shared offline, accessibility and cleanup cells | prior O1 and historical `24ae14a` cleanup remain filed; shared update and console action/refresh changes require current-package O2 reruns. Earlier Narrator, UIA and unfocused capture observations do not qualify changed behavior | partial functional: earlier native focus, VoiceOver speech, state matrix and restoration remain filed; current update and action/refresh controls, exact final offline lifecycle and cleanup remain owed | partial at exact `eab017e5`: native input, disabled/destructive states, populated-provider controls, startup toggle, daemon loss/recovery and isolated Orca callbacks were observed. Exact images and the whole O2 matrix remain owed. O1 lacks an isolated offline snapshot. Recorded test processes exited and original accessibility flags were restored. Two generated payloads were removed; the installation/provider state and original artifact remain for phone continuation, so C1 is partial | not run: host functional qualification is incomplete |

## Completion ledger

| host | cells | result |
|---|---:|---|
| Windows x64/arm64 | W01, W02, F01, W03 through W11, O1, O2, C1 | historical qualification at `24ae14a` is not a current-source pass for shared update changes or the `bb8fb0a8` console action/refresh fix. Rebuild and rerun affected W07, failed-update W09, W06 restart/action and O2 controls. Preserve unchanged observations, including prior O1, separately. W11 producer results do not establish unavailable ARM64 installed-product behavior. W02 and held-candidate assertions remain post-merge work |
| macOS Intel/Apple Silicon | M01, M02, F01, M03 through M06, O1, O2, C1 | partial functional: earlier Apple Silicon configuration, phone watch, accessibility and restoration remain filed. The exact current unsigned PKG must rerun affected lifecycle/update and shared action/refresh behavior, with Tailscale pairing and cleanup still owed. Intel hardware remains unavailable. M02 and named signed-identity assertions remain post-merge trust work |
| Linux x86_64/aarch64 X11/Wayland | L01, L02, F01, L03 through L06, O1, O2, C1 | partial functional against exact `eab017e5` on virtualized Ubuntu 26.04 x86_64 GNOME Wayland. Three closed sessions record install, input, restart, private runtime, provider and lifecycle assertions individually. Public update failure and twelve unsigned integrity negatives passed. Exact app-only visuals and complete O2 remain owed; capture is a host API limit, not an owner-only action. F01 is blocked before device enumeration by host ADB connection refusal. O1 lacks an isolated offline snapshot. aarch64, X11 and bare-metal variants remain not run. Processes and accessibility settings were cleaned up, but C1 preserves attended installation/provider state and retained artifacts. Signing does not block independent functional work |
| WSL x64/arm64 | S01 through S06, O1, C1 | pre-merge functional qualification is not run: release-equivalent unsigned assets are required. Production attestation is a separate post-merge trust lane |

The shared update-source repair still requires affected Windows W07,
failed-update W09 and O2 Settings update-control reruns, plus macOS M06 and
its update controls. WSL must exercise its current public installed CLI path.
The shared console action/refresh repair at `bb8fb0a8` additionally requires
affected restart/action and O2 reruns on Windows and macOS. Linux observations
at `eab017e5` cover only their explicitly recorded assertions; they do not
qualify another platform. Earlier platform passes remain historical for
changed behavior. Unchanged machine and phone observations are not invalidated
without an affected behavior change.

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

The owner approved the exact packet on September 30. Its manifest SHA-256 is
`b2e1d2b29e88bca626e973bfc8234305945280331cdfad6e43342a3b64874c41`.
Existing Version 1.0 terms are unchanged. Finalization identified a missing
canonical RTF rendering and incorrect review-file membership. Derived copies
record those corrections separately and preserve the original reviewed bytes.
The earlier draft-refusal diagnostic used the wrong target spelling; it did
not establish an approval-specific refusal. A corrected Rust-target invocation
did reject the draft for missing approval. Both attempts remain in evidence.

Two retained preparations also expose a reproducibility finding: 39 generated
`uv_cache.json` timestamps and their 39 `RECORD` files differ despite identical
wheelhouse identity. The Linux assembly repair removes only this install-time
metadata and uses a new immutable generation recipe. A fresh Ubuntu 24.04
preparation and exact packet rebinding have now passed at runtime source
`07c7057db797c10dc3842a7e32427a40cfc849f7`. Workflow `36750477603`
retained artifact `11114548031`; independent inspection verified all 5787
receipt members and all 6257 archive members, including directory modes.
The executable is 65513992 bytes with SHA-256
`a471ed1a85e69e3641033eafe875cb01004cc41bd113d593fe5911dff7f585ee`.
The private payload manifest SHA-256 is
`9a006cd5742ef0aa910b3d2c2e45e35120835adffd4b26ba841e82f4a31157a7`.
The refreshed corresponding-source delivery passed both an offline rebuild
and a modified-source rebuild. Its finalized package-input manifest SHA-256 is
`5337cdef2314a2b0a96819f9ea5c10f52faa90acec3196783e4fcc84f0e82931`.
The derivation carries the prior approval of unchanged terms, licenses,
components and source grants; it records changed product sources and does not
claim separate owner review of the new hashes. Actual-payload validation
passed with 825 components and 5283 legal files. AppImage assembly and all
installed-product observations still remain owed. Earlier payload hashes are not
relabeled as the new product. Windows and macOS assembly remain unchanged;
Linux and WSL payload-dependent assertions require rebuilt artifacts.

The following preparation results describe the `07c7057` source before the
later AppImage attempts and source repair below. The host is Ubuntu 26.04
x86_64 GNOME Wayland inside VirtualBox:

- L01 and L02: pending registered AppImage assembly from the validated inputs,
  not owner approval or signing. A
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
  observations only, not a visual or accessibility pass. A disposable-window
  preflight found that this host's GNOME portal 50.0 exposes nonselectable rows
  without native activation actions, while GTK 4.22.2 rejects AT-SPI focus.
  No capture was produced. This is an accessibility implementation gap, not a
  proved protected-permission restriction. No unrelated window was activated
  or captured; native Cancel and OK closed the test dialogs.
- C1: partial preparation cleanup only. Preserve the exact review packet and
  preparation for continuation; final installed-product cleanup remains owed.

aarch64, X11 and bare-metal hardware-specific behavior were not run because
this host supplies none of those variants. Full Rust tests, Clippy, formatting,
1426 Python tests, secret checks and E2E gates passed for the repaired source.
All required implementation checks completed successfully. No installed-product
Linux cell inherits those source or CI results. Nothing was merged, signed,
tagged, published or released.

### Linux AppImage continuation on September 30

Workflow `36755348343` successfully produced the registered AppImage at exact
source `70424be6ead925c93d85f5dd95684a4a87c77dd3`. Retained artifact
`11117000586` contains `Vadgr-0.5.0-linux-x86_64-installer.AppImage`,
577468920 bytes, SHA-256
`f427ae175373ea4f3fa19977ed1b12b4d0e6ab53a9f50c999ef0e586eed705bb`.
Its canonical development receipt is 2665956 bytes, SHA-256
`f5a3f958a507af94a8a9186c224754617f952daf41dde31ccebdffa05b678cd0`.
Independent inspection matched all 11075 AppDir members, including file modes
and confined relative links. All preparation members match the retained
`07c7057` runtime exactly. These are unsigned, non-publishable bytes.

L01 normal launch failed twice with `reading release manifest metadata` before
the terms window. Both attempts exited 1. The isolated XDG roots and owner
command shim remained absent. This is an installer implementation finding:
the unsigned producer emits a development receipt, but preflight unconditionally
requires a production manifest. It is not an unavailable-signing prerequisite.
The repair and rebuilt functional rerun remain in progress.

The newly retained legal source also exposed a repository-gate defect on all
three operating systems: three exact Python files serving legal source delivery
were mistaken for product implementation. A narrow path-and-hash exception
preserves those files unchanged and rejects modified bytes or new paths. The
controlled regression failed without the exception and passed after restoration.
Full local Rust, Clippy, formatting and Python gates passed afterward. CI must
rerun on the corrected test commit. No runtime code changes in this gate repair.

### Linux source repair and rebuild status at `3a9473c`

The earlier `70424be6` AppImage failed before terms a third time. All three
failed attempts remain retained; no rebuilt installed result replaces them.
Source `3a9473c8b34685b81b7b46a0a909496fa0cacc95` adds an isolated,
default-off compile-time Linux development mode. It binds exact source and
development receipt identities without a runtime trust override. Production
trust remains unchanged, and final producers reject development bytes.

Source gates passed: production Rust 534 tests with 1 ignored; development
Rust 561 tests with 1 ignored; Python 1528 tests, 60 skips and 64 subtests.
All 38 CI checks are terminal: 35 passed and 3 skipped. These are not E2E
results. The refreshed source delivery contains 173 product source files,
557 complete crate archives and 519 compiled dependencies. The 158 delivered
resolution-only stubs were not compiled.
Independent native offline baseline and modified-source builds passed in
489.226 and 496.337 seconds using separate target directories. The modified
source marker was verified. These builds do not establish Ubuntu 24.04
artifact byte reproduction.

The refreshed Linux packet is adopted with 825 unchanged components and
unchanged terms. Its 12 generated input changes are a mechanical derivation,
not a new approval decision. The 5286-file packet's inventory SHA-256 is
`19496c2ae9fd9bf0960c6f0829fca023abf7f6ae775e33fcae2917856785d998`.
The final privacy classification verified 467 exact upstream fixtures, with
zero blocked findings and no owner credentials or private paths.
No current AppImage download, installed execution or functional cell pass is
claimed. L01 through L06 and O2 require the rebuilt registered vehicle and
their live assertions. F01 and phone assertions remain pending while the owner
is away. Protected runtime authorization and publisher trust remain post-merge.
O1 remains not run without an isolated offline snapshot. This virtualized
Ubuntu 26.04 x86_64 GNOME Wayland host supplies neither X11, aarch64 nor
bare-metal coverage. C1 has partial source cleanup only: 3308920832 bytes were
reclaimed, while source and evidence remain preserved.

### Linux receipt ordering finding at `43346b79`

The exact hosted AppImage from source
`43346b79d87db788696c101bee3dda88b1616ec9` has 577550840 bytes and SHA-256
`fbfc24ed18085c9c24febc64ba4b6d30a02b164cf5e567b0bfffb2733b98c8f3`.
Its retained artifact is `11122518049` from successful producer `36768523412`.
Independent receipt, inventory, source correspondence and runtime checks passed.
The native public launch nevertheless failed twice before terms with
`unsafe or unordered qualification member`. Both attempts exited 1 and left
the isolated XDG roots, runtime state and command link absent. L01 remains
failed until the rebuilt live rerun; no install pass is claimed.

The producer sorted Python path components while the native verifier requires
complete POSIX path strings. The receipt contains 37 ordering inversions.
The producer now emits that required string order. Three representative
directory-prefix regressions failed before the fix; all 28 targeted tests then
passed, followed by 1531 Python tests, 60 skips and 64 subtests. Rust's existing
canonical-order and duplicate refusals remain unchanged. The fix affects the
Linux development receipt producer, not Windows runtime or package behavior.
The matching source delivery now records snapshot
`753c730c9f444a36d0a6b17efa2c10e5b51b88a2`. Of its 173 retained application
files, only the producer script changed. The complete source manifest digest is
`800b564ce4753cf0a91e2d6faf2667caaad1c4fc2f40ec035e805752e627c473`.
The original two measured source-only builds remain historical observations.
Their reuse gate verifies unchanged compiler inputs, recipes, vendors and proof
bytes; it does not claim new builds. The refreshed package passed validation
for all 825 components and 5283 payload-input files. Its inventory digest is
`bbc34199166c64f87699f62e4ecbaababd35a9015270520b4435af6b8a5ad708`.
A new retained AppImage and native rerun still must close the failed cell.
The original failures remain retained.

### Linux installed observations at `d462eaaf`

Successful producer `36774168663` retained artifact `11124544877` for exact
source `d462eaaf83b9cfc99e3c1920b7a5bb88cc929da2`. Its registered AppImage
has 577538552 bytes and SHA-256
`060793e5617566c75e194d145ce7834ff3a8479faba3dcc2682258f207c91b26`.
Independent verification covered its receipt, 11075 AppDir members, source
correspondence and unchanged private CUA payload. An interrupted extraction
remains retained without an invented exit code.

Native AT-SPI drove terms decline with exit 0 and no product-root mutation,
then acceptance, installation and Open Vadgr. The installed vehicle matched the
retained digest. Selected CLI/API machine fields matched. Restart replaced the
daemon PID and restored health. Private Python reported 3.12.14, and the
installed payload identified CUA 0.7.9. These observations are partial slices,
not complete L01, L02 or L04 passes.

Two native accessibility defects were reproduced. Unchecked Install incorrectly
advertised enabled/clickable semantics, though the installer guard correctly
prevented installation. Machine name advertised editable state, but native
EditableText replacement failed twice. The repair retains exact dependency
versions and grants while correcting Linux state/action mapping and adding
guarded whole-value replacement. The installer also renders the approved terms
headings, emphasis and lists without changing their verified legal bytes.
Controlled negative regressions and the full source gates passed; refreshed
source delivery, a rebuilt AppImage and actual native reruns remain owed.
The Linux-only runtime changes do not establish another platform's pass.
The shared package-input binding changes require each affected producer to
regenerate and validate its exact source bindings before using a new artifact.

Two WINDOW-only portal attempts could not select the intended row through
native accessibility and yielded no image. The owned chooser was cancelled.
No visual verdict, owner-only permission verdict or desktop-crop substitute is
claimed. The failed attempts remain in private evidence PR #176.
After acquisition evidence was pushed, four validated intermediate copies were
removed, reclaiming 3197554688 allocated bytes. The exact AppImage, receipts,
installed test state and live continuation processes remain. C1 is incomplete.

### Linux accessibility rebuild at `f8683e30`

The corrected source is `f8683e303d3405b998156a15791d2d9524055e4b`.
Production Rust tests passed with 523 tests and one ignored; development Rust
tests passed with 565 tests and one ignored. Both Clippy configurations and
formatting passed. The final Python suite passed with 1557 tests, 60 skips
and 64 subtests. These are source results, not installed functional verdicts.

Two separate offline source builds passed with Rust 1.97.1. Each compiled
519 dependencies, including the two exact local accessibility patches and no
resolution stubs. The modified Plasma description reached newly compiled
metadata. The documentation-only edit changed that metadata, while the final
executables had equal hashes. Neither build claims byte reproduction of the
Ubuntu 24.04 package producer. Source delivery retains the unchanged legal
grants and original approval lineage; it does not claim a new owner approval.

The old `d462eaaf` installer also accepted two native Close actions without
closing. A fresh compositor window chooser still listed the installer after
the test console stopped. The first attempt exists only in the tool transcript;
the second attempt and diagnostic cleanup are retained. The cause remains
unresolved. The rebuilt installer must repeat Close before and after Open Vadgr.
An accepted accessibility action is not a successful Close verdict.

After the source proof evidence was pushed, standard Cargo cleanup and removal
of the two validated proof copies reclaimed 2731048960 allocated bytes.
The final source delivery, proof outputs, installed test state and evidence
remain preserved. This is intermediate cleanup, not a complete C1 result.

### Linux installed observations at `9f16fad0`

Producer `36788098632`, attempt 1, retained artifact `11130494824` from
`9f16fad07f49864f4332d228ae89b84fb94851c6`. The registered AppImage contains
577681912 bytes with SHA-256
`677fff01438b3639272442dd6032eacb63cd74df6e87a23603b47c0fcd6e73ef`.
Independent verification covered the development receipt, 11079 AppDir members,
6257 preparation members, 5785 unchanged CUA members and all 229 delivered
application-source files. These are unsigned development observations on the
Ubuntu 26.04 x86_64 GNOME Wayland VirtualBox guest.

Native AT-SPI now reports unchecked Install as insensitive with no action.
Decline left the isolated product roots and real command shim absent.
Acceptance installed the exact retained vehicle. Close before opening the
console ended the installer process; Close after Open Vadgr remains owed.
The earlier failure is not erased by the narrower successful sequence.

Native EditableText replacement saved a Unicode machine name, role and workspace.
The console and CLI/API agreed after Save. Native autonomy selection also
persisted. The first accepted Restart action did not replace the daemon PID.
A focused retry replaced it and restored health without losing the saved fields.
The first attempt remains an unresolved observation, not a proven cause or pass.
CLI edits and same-value no-op behavior passed. CLI and API both rejected a
read-only platform edit without mutation. Required grants stayed checked and
disabled; this host offered no optional grant variant.

The installed update check rejected its absent update origin without changing
the package or healthy daemon. This is not download-failure coverage. Rollback
truthfully reported no verified previous generation. Native Repair restored an
intentionally changed installed vehicle to the exact retained digest while the
same daemon remained healthy. Retained-generation update and rollback branches
remain owed where their prerequisites can be produced legitimately.

Native uninstall cancellation preserved installation and state. Confirmed
uninstall with purge off removed the package, command, desktop and autostart
entries and stopped the test daemon. The logical persistent-state identity
remained unchanged. Reopening the same retained installer then requested the
same accepted terms again. This is a finding, not a completed reinstall pass.
Declining preserved the isolated state for the repaired rerun.

Twelve development-integrity negative launches rejected changed architecture,
platform, source identities, development/trust flags, receipt size/hash, missing
receipt and changed vehicle bytes before mutation. The first helper redirected
HOME; those initial records remain explicitly limited. All twelve corrected
reruns preserved actual HOME, the absent real command shim and isolated roots.
Neither group proves extraction or final publisher trust.

Orca's bounded probe produced no allowlisted product-label speech. A service
handoff timeout and earlier replacement race remain recorded. The pass-enabled
reader service was restored. WINDOW-only portal selection still refused the
exact row through native accessibility and produced no image. No visual,
screen-reader or protected-owner-boundary pass is claimed. Ordinary installer
and console controls used native accessibility, not pointer or desktop capture.

### Linux retained-assent repair at `b87938f2`

The installer now reuses only an exact retained terms version and digest.
First acceptance or a changed version still requires unchecked explicit assent.
Changed bytes under the same version fail before installation. The installer
revalidates the retained acceptance immediately before mutation. Reviewed terms
bytes and their version are unchanged.

The controlled regression failed two assertions without the fix and passed all
five focused tests after restoration. Full default and development Rust suites
passed 523 and 568 tests respectively, each with one ignored. Both all-targets
Clippy configurations and formatting passed. The final installer source digest
is `96b6b5467547d1397df0db3a4aa4cd944f36a67a6198cc7d9692facfda93d32a`.
These source results do not close the installed reinstall finding. Refreshed
source delivery, a newly retained AppImage and affected native reruns are owed.

The same change corrects test-only texture cleanup that failed debug CI.
The separate Windows fixture repair binds canonical UTF-8/LF bytes instead of
host-dependent text newlines. Its controlled regression failed before repair
and passed after it. Neither repair changes Windows runtime behavior. The Linux
installer change invalidates affected installer/reinstall observations until
rerun; no prior platform result is silently promoted to the new artifact.

Raw observations and both initial and corrected failures remain in private
evidence PR #176. L01 through L06 and O2 remain partial, not whole-cell passes.
F01 and phone-dependent assertions remain pending for the attended continuation.
O1 is not run without a pre-existing isolated offline snapshot. No networking
was changed. X11, aarch64 and bare-metal variants remain not run on this host.
C1 is incomplete: the isolated preserved state and exact vehicles remain needed
for reinstall and attended assertions. Signing and immutable-candidate trust
remain separate post-merge obligations.

Both new offline source builds subsequently completed with recorded exit 0:
471.931 seconds for the baseline and 469.959 seconds for the modified source.
Each compiled 519 dependencies, both bound local patches and no resolution
stubs. Independent recovery checks verified both build-finished events,
retained executable hashes, native development notes and the newly compiled
source-marker metadata. The outer launcher did not record its final exit or
end time; neither is reconstructed. No duplicate build was run for appearance.

The refreshed source manifest digest is
`b1db47504a64270ddb5b70bdab430e5c9f736bf28064f502f26b37706b4f0e3e`.
All three sealed source volumes passed independent verification. The derived
5290-file package retains all 825 component identities, existing legal grants
and terms. Its inventory digest is
`23660704299e6932abbefb10b28ce1e902764a3c8dfa921ae1c00fa214db75fe`.
Fresh decoded privacy checks classified 467 exact upstream fixtures with no
blocked findings. Opaque fixture contents are not claimed fully decoded.
This is a mechanical corresponding-source refresh, not new legal approval,
publisher trust or an installed E2E verdict. Exact rebuilt AppImage acquisition
and affected native reruns remain required.

### Linux retained AppImage at `026a0281`

Producer run `36797878174` completed successfully for source
`026a0281a3982c165764c8b1d97c63b3c24a92ff`. Retained artifact `11134762755`
contains `Vadgr-0.5.0-linux-x86_64-installer.AppImage`, 577645048 bytes, with
SHA-256 `e965004a1f669e0af3c9bb1fca6d966e05dbba0180189a0effb99e956c24bbad`.
Independent acquisition checked the receipt, all 11079 AppDir entries, 6257
preparation entries, 5785 CUA payload entries and 229 source correspondence
files. This establishes exact unsigned development bytes, not publisher trust.

Native observations on the virtualized x86_64 GNOME Wayland host:

- L01: ordinary launch exposed unchecked assent and a genuinely disabled
  Install control. Decline left every isolated product root and command link
  absent. Required rendered-terms inspection remains owed without an exact
  application-only capture.
- L02: installation completed and the daemon answered health. Open Vadgr
  started the installed console. Close worked before opening another console,
  but remained pending when that console covered the installer. This failed
  attempt is retained; it is not a complete installation or visual pass.
- L03: all twelve development-integrity negative cases rejected before XDG
  mutation and preserved the existing command link. Normal and extraction
  launches reached the terms controls; extraction decline preserved empty
  product roots. The extraction wrapper and child exited, but left their
  extracted AppDir. Production attestation and immutable identity remain owed.
- L04: installed CLI and API machine snapshots agreed. Native restart changed
  the daemon PID and returned healthy. The installed mount supplied private
  Python 3.12.14 and CUA 0.7.9. The public API reported computer use enabled but
  its managed runtime unavailable; the authorization envelope and bundle were
  absent. Two direct bootstrap probes are retained as nonqualifying attempts,
  not as a managed-admission or task oracle. No provider call ran. Phone and
  required visual assertions remain owed.
- L05: the update entry specifically refused an absent update origin while
  the exact binary, daemon and health remained unchanged. No manifest download
  occurred, so this does not close the download-failure assertion. Rollback
  truthfully named the absent verified predecessor. Native Repair restored a
  deliberately altered package-owned AppImage to its exact retained digest.
- L06: cancellation preserved the isolated state. Uninstall-preserve removed
  package and launch entries; same-artifact reinstall found the identical
  logical state and reused exact terms acceptance. Empty and wrong typed purge
  confirmation kept deletion disabled. Separate native selection and exact
  typed confirmation removed only the isolated Vadgr state and package. The
  remaining test console was stopped. Required visual observations remain owed.

The covered-window investigation reproduced the Close failure independently.
A separate sibling console covered a fresh terms installer; accepted Decline
remained pending until the cover closed. The same bytes exited while their
cover remained open when only the installer process disabled vertical-sync
waiting. No host graphics setting changed. This controlled diagnostic supports
a Linux rendering fix, not a pass for unchanged ordinary package behavior.
The fixed source, refreshed corresponding-source packet, rebuilt retained
AppImage and affected native reruns are still required.

O2 remains partial. The initial host-session screen reader stalled even with
no Vadgr process. A subsequent isolated accessibility-bus preflight on the same
Wayland desktop produced actual Orca speech for the terms acceptance control
and Decline button. Orca retained its normal auxiliary display while only the
product used the Wayland-only environment. This terms-only preflight does not
close the installed state matrix or prove ordinary-session interoperability.
The window-only portal selector still refused native row selection and focus;
no exact image was obtained. Earlier failures, transient tree-discovery attempts
and accessibility-setting restoration attempts remain retained. No owner
inspection or desktop crop substitutes for these oracles.
F01 remains pending for attended continuation; O1 requires an existing isolated
offline snapshot. Unavailable X11, aarch64 and bare-metal variants remain not
run. C1 is not complete. Exact vehicles, source, evidence and remaining scoped
test artifacts are retained for the rebuilt continuation. No release action ran.

The update investigation identified an implementation finding rather than a
signing prerequisite: the Linux package had no default update origin and the
installed CLI provided no explicit source. The repair adds an official Linux
release-download fallback and `vadgr update --source URL_OR_DIRECTORY` while
retaining manifest, signature, sequence and target verification. Development
installations may check a source but cannot apply a signed generation; the
console exposes that restriction. Regression results alone do not close L05:
the rebuilt AppImage must exercise a reachable failure and preservation through
its public installed path. Positive updates and unavailable predecessor
rollback must not be invented for this first release.

### Linux retained AppImage at `ef712d64`

Producer run `36812952675` completed for source
`ef712d64274b161d5f10794b2363c8c7dc248633`. Retained artifact `11139969130`
contains `Vadgr-0.5.0-linux-x86_64-installer.AppImage`, 577759736 bytes, with
SHA-256 `c2ef221bb810291bda0852a63a1d2055c86d6dee95824c5ceeaeb85816fe419b`.
Independent checks verified its receipt, 11079 AppDir entries, 6257 preparation
entries, 5785 CUA payload entries and 231 source correspondence files. These
are unsigned development observations, not production trust qualification.

The virtualized x86_64 GNOME Wayland continuation observed these assertions:

- L01: unchecked assent kept Install disabled. Native Decline exited without
  product mutation. The first inventory comparison included Orca's own initial
  files; a second decline after that initialization preserved the complete
  isolated inventory exactly. Both attempts remain retained. Terms visuals
  remain owed.
- L02: installation and Open Vadgr succeeded. The installed vehicle matched
  the retained hash and health was available. Native Close exited the unfocused
  installer while the console and daemon remained alive. No exact image proved
  pixel occlusion. A ready-state idle sample lasted 30.444909613 seconds with
  zero measured process and main-thread CPU. The loading sample lacks a final
  loading-state bracket and is not a complete loading-CPU verdict.
- L04 and O2: native Unicode name, workspace, multiline prompt and autonomy
  edits agreed with independent CLI/API reads. Cancelling a second draft kept
  the saved values. The private payload inventory matched its packaged manifest;
  this pass did not execute its interpreter or a billed task. Actual isolated
  Orca speech covered machine fields, tabs, provider selection and update
  controls. An accepted Restart action did not change the daemon identity.
  This remains a failed observation, not a restart pass.
- L05: the console reached `downloading release-manifest.json` as its failure
  and preserved the package, receipt, current link, daemon, health and selected
  machine state. The installed CLI instead selected the source-checkout updater
  on two attempts. The public AppRun alias omitted the installed receipt root.
  This is an implementation defect; console success cannot close the CLI
  assertion. Rollback remained disabled with the absent-predecessor reason.
- L03 negative cases, Repair and L06 were not repeated in that first bounded
  session. Their earlier results remain historical, not new passes.

A deterministic regression separately reproduced an enabled console action
being displaced by a due background refresh. Two unchanged-source runs called
refresh instead of restart. This proves the race, not its timing in the earlier
native observation. Both fixes require a rebuilt AppImage and affected native
reruns. A shared console fix also requires affected action/refresh reruns on
other native platforms; prior platform results do not cover changed behavior.

The bounded session ended with public daemon stop returning zero. Its final
process inventory hit a retained helper permission error, and its checked
console required fallback termination. A subsequent independent process check
found the recorded controller, private bus, reader, console and daemon absent.
The isolated installation and logical state remain for continuation. This is
not C1 completion. Exact app-only visuals, remaining accessibility states,
phone observations and the unavailable offline snapshot remain owed as above.
No merge, signing, tag, publication or release occurred.

A second bounded session used the same retained bytes. Native Repair restored
an atomically replaced, deliberately altered package-owned AppImage to the exact
retained digest. Its verified cache and receipt stayed unchanged. The daemon
identity, health and saved machine fields remained intact.

L06 cancellation preserved the isolated installation. Uninstall with deletion
off removed the package, command and launch entries while retaining identical
state-file hashes. The first retained-vehicle reinstall launch exited one; only
its output hash and byte count were retained, so its cause is not established.
An unchanged repeat exposed retained terms acceptance, installed successfully
and found all selected saved machine fields through the public CLI.

The separate purge dialog defaulted off. Empty and wrong confirmation text
kept Uninstall disabled, and the native action helper refused each attempt.
Independent native text readback matched both the wrong phrase and the exact
required phrase. Only the latter enabled Uninstall. Confirmed deletion removed
the isolated package, state, command and launch entries and stopped its daemon.
Orca produced the destructive-dialog, cancellation and confirmation-field speech
callbacks. Exact images and the complete O2 matrix remain owed.

The second session retained its early reinstall failure, transient accessibility
warning and final helper inventory permission error. Its checked remaining
console required fallback termination. An independent check subsequently found
all recorded session, reader and product processes absent. This is scoped
test cleanup, not final C1: retained artifacts, source-build work and temporary
host accessibility settings remain for the corrected-package continuation.

### Linux retained AppImage at `eab017e5`

Producer run `36820973289` supplied retained artifact `11143626995` for source
`eab017e5e100b9422d462338d661cb3cb0ad9a37`. The exact unsigned AppImage has
577767928 bytes and SHA-256
`c6ef7d4cdb968b10594c5228d4c004ca829811462bca6a512e6dea8b0f2992c3`.
The following observations cover only the closed native-first and extraction
sessions on virtualized Ubuntu 26.04 x86_64 GNOME Wayland, plus the separately
retained development-integrity negatives. They do not include the provider
continuation.

- L01 and L02: native Decline preserved the complete scoped product inventory.
  Installation reached success and health; Open Vadgr launched the installed
  console. Native Close exited the installer while another application was
  active and the installer was not active. Accessible extents do not prove
  pixel occlusion. The ready-state CPU sample lasted 30.432530359001248 seconds:
  0.032859574547478364 percent of one logical CPU for the process and zero for
  the main thread. This is not a loading-state CPU verdict or a visual pass.
- L03: all twelve individual development-integrity negatives exited one with
  their specific refusal and no scoped mutation. Normal and extraction
  launches reached the terms controls. Extraction Decline preserved the
  complete product inventory; its wrapper exited, but its confined extraction
  output remains. This is not production signature or attestation evidence.
- L04: native name, multiline prompt, workspace and autonomy edits matched
  independent reads. Cancellation kept the saved values. Selected public
  `vadgr config set` edits appeared in native fields and agreed with the API.
  CLI read-only ID assignment exited two; API ID and daemon-version changes
  returned 422 without changing machine fields. A no-op retained the selected
  machine snapshot. Native Restart changed the daemon identity, restored
  health and retained that snapshot. Earlier busy trees and refused actions
  remain retained; a native focus action preceded the successful restart.
  These observations do not establish a new permanently stuck-refresh defect.
- The installed read-only payload matched its inventory. Its own Python ran
  with `-I -B` and reported Python 3.12.14 plus CUA package metadata 0.7.9.
  Health reported computer use unavailable. No CUA bootstrap, managed-runtime
  adoption or provider task ran in these closed sessions. The initial
  independent health helper refused an overly narrow listener precondition;
  its corrected, identity-bound read returned healthy. Both records remain.
- L05: the public installed CLI and Settings reached
  `downloading release-manifest.json`, preserving the exact package, receipt,
  current link, healthy daemon and selected machine state. This supersedes the
  earlier installed-alias failure for this exact artifact. Unsigned apply
  refused; rollback stated that no verified previous generation exists.
  Native Repair restored a deliberately altered owned AppImage to its exact
  retained digest; the cache, receipt and machine state remained intact.
  Positive update/rollback and downstream trust-gated fault assertions remain
  owed against a subject that meets their prerequisites.
- L06: cancellation preserved the installation. Uninstall without deletion
  removed package and launch entries while retaining identical state-file
  hashes. Same-artifact reinstall reused terms acceptance and recovered the
  selected CLI/API state. Empty and wrong typed confirmation kept deletion
  disabled; native readback verified both wrong and exact input. Only exact
  confirmation enabled the separate purge, which removed the isolated
  package and Vadgr state. The remaining checked console was stopped during
  scoped session cleanup.

Isolated-bus Orca produced actual speech callbacks, and native structured
oracles covered input and lifecycle states. These are partial O2 observations.
Exact unfocused application-only images, rendered-terms inspection, the
complete accessibility matrix and phone assertions remain owed. The portal
selector limitation is a host API boundary, not an owner-only action.
O1 still lacks a pre-existing isolated offline snapshot. No host networking
was changed. The closed sessions ended without their recorded product
processes, but extraction output, retained artifacts and continuation work
keep C1 incomplete. aarch64, X11 and bare-metal variants remain not run.
No whole L01, O2, trust, merge or release pass is claimed.

### Linux provider continuation at `eab017e5`

A third isolated native session installed the same retained AppImage. Native
API-key entry used the password field after the private screen reader exited.
No secret value, password readback or secret-bearing capture was retained.
One bounded Connect action selected Gemini 3.7 Flash and completed readiness.
One separate native model selection made Gemma 4 26B A4B IT the default.
The installed CLI agreed with both native default states. The paid action had
a reviewed USD 1.50 allowance; this is not a measurement of actual spend.
No computer-use task or paid fallback ran.

An independent identity-bound provider API check confirmed connected,
available, current-catalog and matching machine/provider default states.
A native model refresh changed the catalog verification identity while
preserving the model set and selected default. Disconnect cancellation kept
that state. Actual disconnect remains for the attended cleanup, so the prepared
provider is available for F01 without another paid connection check.

Launch at login toggled off and on through AT-SPI. The isolated autostart file
disappeared and returned. Its restored command uses the version directory
rather than the installer's current alias; both resolve to the exact retained
vehicle, and all other entry bytes match. This is not a future-update verdict.
Legal Open launched an isolated Files window whose native frame was named
legal. That limited observation is not exact-location or rendered-content proof.
No exact image was obtained.

The public CLI stopped the test daemon. Later native state reported the machine
and transports unavailable. Two attempted native recovery actions were refused
while the control was unavailable. Public CLI Start restored health and the
same default. Its AppImage wrapper caused the strict process-discovery helper
to reject the different executable identity; a separate check bound that
wrapper to the exact retained artifact and the actual daemon to the expected
ELF. Both exited naturally after the final public Stop. Session cleanup stopped
the checked console and private reader, with no product processes in its final
scoped inventory. Failed helper attempts remain retained.

The host ADB server probe returned connection refused before a device list.
It neither started guest ADB nor contacted a phone. F01 cannot yet reach its
physical-camera boundary; no phone connection or scanner-ready state is claimed.
The isolated installation, terms acceptance and provider/default remain for
attended continuation. This is not final C1. O2 remains partial because exact
visuals, the complete state matrix and phone controls are still owed.

After those sessions closed, the original two accessibility settings and two
accessibility-bus flags were restored to false and verified. The existing
failed reader-service state remained unchanged, with no process or service
reset. Thirty-two recorded private process IDs were absent. Three exact
pre-existing processes denied environment inspection; the evidence records
that limitation and does not claim global process absence.

The sealed tampered-vehicle copy and extracted test payload were removed after
fresh identity, retained-evidence and process-reference checks. Their allocated
size was 1650647040 bytes; 428 retained hashes remained unchanged. Earlier
standard Cargo clean operations removed 1705566208 and 4266606592 allocated
bytes from the two identified build caches. The exact original artifact,
source, evidence and isolated phone-continuation state remain. Final C1 still
owes the attended installation, test credential/device and remaining artifact
cleanup; none of that state is presented as already removed.

### Linux pairing cancellation at `eab017e5`

On 2026-10-01, a separate isolated session reopened the same installed AppImage
and retained provider state. Native Pair device opened the pairing dialog;
the exact available Cancel pairing control accepted one native action.
An independent `DELETE /api/auth/pair` returned
`404 / PAIRING_WINDOW_NOT_FOUND` about 14 seconds after opening, well before
the five-minute expiry. Independent before/after reads found no devices and
the same provider/model default. A transient busy tree followed cancellation;
native focus preceded a fresh stable tree with the ordinary controls enabled.

Earlier no-QR observations remain historical. This session created a transient
pairing QR/code but retained neither its value nor an image. No phone action or
model call ran, and no visual or whole O2 pass is claimed. Public Stop and
scoped cleanup closed the session. Its recorded processes were absent, and
the two owner accessibility settings and two bus flags remained false.
The prepared installation and provider remain for the phone continuation.

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
