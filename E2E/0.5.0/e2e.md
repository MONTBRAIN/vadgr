# 0.5.0 - the product is installable: E2E runbook

> **Implementation:** `feature/0.5.0-distribution` at
> `d96e4fe40f22e7ebcadc0232fb9ecd13005dc7c9`; the PR resolves after the first
> target passes. **Private evidence PR:** resolve before the
> first live cell. Do not create a replacement PR.
>
> **Status: development qualification in progress.** No cell below is a formal
> release pass. Signing identities, reviewed terms, release public key, CUA
> 0.7.8, candidate artifacts and private evidence boundary remain prerequisites
> for the final candidate pass.

This runbook proves that a published Vadgr release installs, operates, repairs,
updates, rolls back and uninstalls without a checkout, system Python or separate
CUA installation. Read this file and [the shared rules](../README.md) completely
before the first action. Raw evidence belongs only in the private evidence PR.
The negative control records **terms declined** and proves zero mutation.

## Fixed subject and evidence boundary

Record the implementation commit, signed tag, candidate workflow run, artifact
names, byte sizes and SHA-256 values before any host runs. Every host downloads
the same immutable release assets. A rebuild invalidates the affected cells on
every host. Public status contains outcomes and finding identifiers only. Raw
installer logs, screenshots, signature reports, journals and wire responses stay
under the private `e2e_evidence/vadgr-0.5.0/HOST_NAME/` boundary. Redact no failure;
prevent credentials and owner-private paths from entering the capture.

## Paired surfaces this pass depends on

| repository | released version | exact released subject | what this pass relies on |
|---|---|---|---|
| vadgr-mobile | 0.4.5 | `9ac2324b7de731475ce6c750a34640ac0244f910` | account-independent pairing, machine display and run observation used by the physical-phone cells |
| vadgr-computer-use | 0.7.8 | `af347a0cdd782626a84542f7fd781e23c87d87d2` | the bundled screenshot runtime plus browser discovery and released-broker upgrade handoff |

## Development qualification before the candidate

The host lead may run live development qualification against the exact feature
commit before signed or published artifacts exist. Use an isolated test state
and label every result `development`, never `pass`. The currently released CUA
0.7.5 proved earlier console, daemon and released computer-use integration. It
does not prove the final package contains CUA 0.7.8. An unsigned local package may
prove installer flow and lifecycle behavior, but it cannot satisfy W03 or any
oracle that specifically requires a signature, immutable candidate, clean host
or published release.

Run every unaffected action and oracle now. Defer only the unavailable assertion
inside a cell, then rerun that assertion and any behavior it can affect against
the final candidate. Development findings are real implementation findings and
must be fixed before the candidate is produced.

## Native console driving

The host lead drives every automatable installer, console, CLI and connected
phone action. On Windows, use Windows UI Automation through the AccessKit tree.
Take an app-only client-area capture with `PrintWindow(PW_CLIENTONLY)` under a
per-monitor-aware DPI context. Prove once that capture works while the console
is not focused. After every action, reacquire the UI Automation elements, inspect
the app-only capture against the approved mockups, and verify the result through
the API, process, package, filesystem or journal oracle named by the cell.

The owner acts only when the operating system protects the interaction from
automation or a physical camera must scan a QR code. The runbook's isolated
test-state cells authorize their named destructive operations; the agent drives
their confirmations through accessibility. Prepare the exact state first. Give
the owner one precise action and the visible completion result, then resume control. Do not ask
the owner to click ordinary controls, type a pairing code, take screenshots,
read the UI or report a machine oracle.

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
  bundle; published Minisign public key and offline signature; protected
  candidate run; immutable artifacts and attestations; private evidence PR.
- Windows: clean x64 and arm64 targets where supported, administrator approval,
  Smart App Control target, issued public Authenticode identity and approved
  secure signing route. Signing operations may be billed. Never retry them
  automatically.
- macOS: clean Intel and Apple Silicon hosts, administrator approval, active
  Apple Developer membership, Developer ID Application and Installer identities,
  notarization permission, and an owner present for Login Items, Accessibility
  and Screen Recording. Notarization and certificate use happen only in the
  protected environment.
- Linux: clean x86_64 and aarch64 targets, X11 and Wayland sessions, optional
  FUSE, and separate approval before a distro package manager changes anything.
- WSL: clean x64 and arm64 distributions where supported. No GUI, service,
  autostart or Windows mutation is permitted.
- Functional cells: a test provider account with bounded billing, one physical
  phone where pairing is named, and permission for one harmless screenshot task.
  Supply secrets only through the repository-approved local secret input. Never
  capture their values.

## Part H: protected owner boundaries executed first

Each host lead reaches these boundaries before unrelated unattended cells. Only
prerequisite setup needed to make the protected or physical interaction appear
may run first. The host lead remains responsible for all surrounding actions and
oracles. Windows executes only the Windows rows in this session.

| cell | operating system and architecture | owner/environment requirements | precondition | agent setup | exact owner action | visible completion result | evidence boundary | cleanup | cost, accounts, devices and permissions | result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| W02 | Windows x64 and arm64 where supported | owner is present only if Windows presents a protected UAC prompt | W01 and the pre-install part of W03 pass | start the verified setup, accept terms and continue until the protected prompt appears | Confirm that the prompt names the expected Vadgr publisher, then choose **Yes**. Do nothing if no prompt appears. | setup resumes and shows truthful installation progress | private Windows boundary; capture no protected desktop image | keep installation for Windows cells | one administrator approval if requested; no provider cost | not run: final signed setup is unavailable; no protected prompt may be trusted yet |
| F01 | each native GUI host | owner holds the physical phone with camera permission | installed console and default provider are healthy; agent has opened the prepared QR screen | agent confirms the phone is connected through ADB, enters the provider secret through masked UI without capture, and leaves the QR fully visible | On the phone, open the system camera scanner, scan the visible Vadgr QR code, and approve opening Vadgr Mobile. Stop when Vadgr Mobile shows the prepared machine name. | agent verifies the mobile machine, console device, provider API, daemon lines and transport rows; agent then revokes and repeats pairing by typed code through ADB | matching private host boundary | keep the typed-code device paired for transport cells | phone and camera permission; provider API use may be billed | not run: execute once the unsigned native development installation is healthy on the host |
| M02 | both macOS architectures | owner controls Login Items, Accessibility and Screen Recording | signed package is ready; Terminal and Python grants remain absent | drive installer and console until each protected system prompt or Settings row appears | Approve the Vadgr login item. Deny, then grant, Accessibility and Screen Recording only to the displayed Vadgr Computer Use identity. Stop when System Settings shows both grants enabled. | grants attach to `com.montbrain.vadgr.cua`, not Terminal or Python | private macOS boundary; never export the TCC database | leave grants for M06 | Apple membership, administrator and privacy permissions | not run: signed and notarized macOS package is unavailable |
| L02 | native Linux x86_64/aarch64, X11 and Wayland | owner can approve a package-manager prompt if it appears | verified AppImage is ready and FUSE dependency is absent | drive install until the protected package prompt appears | Verify the prompt names only the documented FUSE dependency, then approve it. Do nothing if no prompt appears. | installer resumes its visible phases | private Linux boundary | keep installation | separate package-manager approval | not run: final verified AppImage is unavailable |

## Part W: Windows cells

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions | result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| W01 | Windows x64, then arm64 | clean desktop; no owner action | no Vadgr product, state or launch entry | agent records product paths, HKCU Run, Start menu and isolated state-root inventory, then verifies fixed artifact hashes | agent opens setup through accessibility, inspects terms, leaves acceptance clear and invokes decline | before/after product paths, HKCU Run, Start menu and state-root inventory | setup closes and creates nothing | private Windows boundary: app-only captures plus inventories | delete download only after evidence is filed | no signing call; elevation must not appear before acceptance | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| W03 | Windows x64, then arm64 | clean Smart App Control target | W02 not yet installed on fresh snapshot for the pre-install half | obtain setup, MSI and manifest from immutable release | agent runs `Get-AuthenticodeSignature` and SignTool verification on setup and MSI; after W02, repeat on cached Burn engine/uninstaller and every installed PE | valid chain, expected publisher and timestamp on each named file | every required vehicle and installed executable is valid; one unsigned layer fails | private Windows signature report | retain clean state for W02 after pre-install verification | no new signature operation | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| W04 | Windows x64/arm64 | none beyond W02 | signed install healthy | record `vadgr machine --json`, API machine and console | edit name, role prompt, autonomy mode, workspace and available grants in console; repeat selected edits with `vadgr config` | all three reads and database persistence after restart | one full machine snapshot; read-only fields rejected; no-op is idempotent | private Windows machine/API capture | restore original settings | none | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| W05 | Windows x64/arm64 | physical phone connected and visible to ADB | F01 paired | agent confirms ADB state and keeps both transports available | agent uses accessibility and ADB to inspect devices, the Machine view's read-only Built-in endpoint/direct/relay details, Tailscale advertised host and port, and connected state, then cancel and confirm revoke | `GET /api/machine` transport diagnostics, API device rows and live socket closure | the accessible Machine values equal the safe diagnostics; unavailable transports say so; long values wrap at the minimum window without horizontal overflow; cancel keeps the device; confirm revokes and disconnects it | private Windows device and app-only capture | agent pairs one device for later task | phone required; no owner action | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| W06 | Windows x64/arm64 | provider account | default provider ready | start one harmless screenshot task | choose Restart Vadgr and observe progress; run task through bundled CUA | daemon PID/health transition and journal result | restart is truthful; task finishes using pinned CUA 0.7.8 and Python without system Python | private Windows daemon/journal capture | delete test run after filing | one bounded provider call; screen permission | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| W07 | Windows x64/arm64 | fault-injection snapshot | W02 healthy | prepare signed candidate with controlled failure at each named phase | inject download, verification, staging, dependency, daemon-stop, commit and health-check failure one at a time | prior setup launch, version and health after each attempt | every failure is specific and prior installation remains runnable | private Windows failure matrix | revert injection after each row | no signing retry; candidate only | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| W08 | Windows x64/arm64 | none | W07 complete | corrupt one package-owned file; keep retained signed source | choose Repair in Settings | MSI log, repaired hash and successful ordinary launch | repair restores only owned files and preserves owner state | private Windows repair capture | none | administrator only if Windows requests it | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| W09 | Windows x64/arm64 | signed previous and next candidate | current candidate healthy | ensure retained prior vehicle exists | update from local signed assets, then choose Roll back | signed manifests, versions, health and owner-state identity | update commits atomically; rollback selects verified prior version; identity/state stay equal | private Windows lifecycle capture | return to fixed test version | signed artifacts already produced; no signing call | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| W10 | Windows x64/arm64 | isolated E2E state only | W09 complete | agent hashes isolated state and records package paths | agent drives uninstall with preservation and reinstall; then selects the separate deletion choice, types `DELETE OWNER DATA` and invokes uninstall | package inventory and isolated-state identity after each operation | first uninstall preserves and reinstall finds state; second separate choice deletes only the isolated Vadgr state | private Windows uninstall capture | reinstall fixed candidate if later cells require it | agent drives all app controls; protected Windows prompt only if shown | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |

## Part M: macOS cells

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions | result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M01 | macOS Intel, then Apple Silicon | clean host; no owner action | no Vadgr app, shim, state or login item | agent records the before inventory and verifies package signature, notarization and staple offline | agent opens the package through accessibility, inspects terms and invokes decline | before/after `/Applications`, shim, state and background-items inventory | installer makes no mutation | private macOS boundary | delete download after filing | administrator must not be requested before acceptance | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| M03 | Intel and Apple Silicon macOS | protected signed artifacts | M02 installed | network off after download | run `pkgutil`, `spctl`, `codesign` and stapler checks on package, app, CUA host and nested code | expected Team ID, hardened runtime, timestamp, staple and no `get-task-allow` | every layer verifies offline | private macOS signature report | none | no notarization call | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| M04 | both macOS architectures | owner | M02 grants active | record helper designated requirement | restart app, restart daemon, sign out/in and launch normally | CUA task and requirement string after each boundary | helper identity is byte-equal and grants survive all launches | private macOS identity capture | stay installed | Accessibility and Screen Recording | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| M05 | both macOS architectures | owner and provider | M04 complete | one paired phone | repeat W04 through W06 on macOS | CLI/API/console, device rows, health and journal | same shared behavior; platform launch uses SMAppService agent | private macOS functional capture | remove test run/device | provider billing and phone | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| M06 | both macOS architectures | signed next package and isolated E2E state | M05 complete | agent captures helper requirement and TCC result | agent drives update, repair, rollback, uninstall-preserve, reinstall and the separate explicit purge confirmation | signatures, requirement, health and isolated-state identities | prior install survives failure; rollback and repair work; MA2 closes across update without new grant | private macOS lifecycle/MA2 capture | agent removes product and test grants after filing | protected administrator or privacy prompt only if shown | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |

## Part L: native Linux cells

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions | result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| L01 | native Linux x86_64, then aarch64; X11 and Wayland | clean graphical session; no owner action | no Vadgr XDG generation, command, desktop or autostart entry | agent records the before inventory and externally verifies manifest signature and AppImage hash | agent opens the AppImage through accessibility, inspects terms and invokes **Decline and close** | before/after XDG data/config, command and state inventories | no product or owner-state mutation | private Linux boundary | remove downloaded files after filing | no root or package-manager action | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| L03 | x86_64/aarch64, X11/Wayland | clean GUI hosts | L02 installed | keep FUSE; prepare extraction test | verify Minisign first, size/hash second; launch normally and with `--appimage-extract-and-run` | signature output, target match and both launches | both paths work; wrong key/signature/target/size/hash fails before XDG mutation | private Linux integrity capture | delete tampered copies | none | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| L04 | same matrix | provider and phone | L03 complete | one provider/default and paired device | repeat W04 through W06 | CLI/API/console, transport and journal | shared console/backend behavior matches Windows | private Linux functional capture | remove run/device | bounded provider call and phone | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| L05 | same matrix | fault-injection host | L04 complete | signed local previous/next generations | inject every W07 failure; repair, update and roll back | `current` link, version receipts, health and state identity | atomic link restores prior generation; repair uses retained verified source | private Linux lifecycle capture | select fixed generation | no root | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| L06 | same matrix | isolated E2E state only | L05 complete | agent records XDG and isolated state roots | agent drives uninstall-preserve/reinstall, then the separate typed purge | exact paths and isolated-state identity | only package/XDG entries removed first; state found on reinstall; purge deletes the exact isolated state root | private Linux uninstall capture | agent removes all test artifacts | no owner action unless a protected package prompt appears | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |

## Part S: WSL cells

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions | result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S01 | WSL x64, then arm64 | clean distribution; no owner action | no Vadgr generation, command or state | agent verifies script attestation and points `RELEASE_DIR` at the immutable local assets | agent runs `./install.sh --source "$RELEASE_DIR"`, inspects the terms and enters anything except `ACCEPT 1.0` | before/after Linux roots plus Windows registry and network snapshots | no WSL or Windows mutation | private WSL boundary | remove temporary download directory | no GUI, elevation or Windows permission | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| S02 | WSL x64/arm64 | clean distributions | S01 complete | local immutable release in `$RELEASE_DIR`; network blocked | run `install.sh --source "$RELEASE_DIR" --accept-terms 1.0` | verifier output, archive inventory, version/target/pins and health | CLI-only install succeeds with CUA 0.7.8/Python pin and no system Python/toolchain | private WSL install capture | keep installation | no elevation or GUI | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| S03 | WSL x64/arm64 | none | S02 clean snapshot | tampered copies | independently alter verifier, public key build, manifest, signature, target, size, hash, traversal and escaping link | exit and before/after WSL/Windows inventories | every case fails before install mutation; Windows registry, DNS, firewall, VPN and files unchanged | private WSL negative matrix | delete tampered files | none | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| S04 | WSL x64/arm64 | provider account | S02 healthy | provider configured securely | run one screenshot task through bundled CUA; compare CLI/API machine config after edits | journal and pin records | task succeeds; machine store persists; no GUI/autostart/service exists | private WSL functional capture | remove run and provider credential | bounded provider call | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| S05 | WSL x64/arm64 | fault-injection distribution | S04 complete | retained previous/next archives | inject failures, update, repair and rollback through `install.sh` | `current`, receipts, health and state identity | prior generation remains runnable and rollback is verified/local | private WSL lifecycle capture | restore fixed version | none | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| S06 | WSL x64/arm64 | isolated E2E state only | S05 complete | agent records isolated state identity | agent drives uninstall-preserve/reinstall, then `--delete-owner-state` and types the confirmation | exact Linux roots and Windows no-change snapshot | state survives first cycle; separate purge removes only isolated WSL Vadgr state | private WSL uninstall capture | agent removes test assets | no owner action | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |

## Part O: shared offline, accessibility and cleanup cells

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions | result |
|---|---|---|---|---|---|---|---|---|---|---|---|
| O1 | every installed target | isolated offline test snapshot | target functional cells pass | start from a test snapshot whose external network is already unavailable; do not change host firewall, DNS, routing or VPN state | agent launches CLI/console, opens bundled legal notices, restarts, repairs, rolls back and uninstalls | process/health, offline files and package receipts | installed product lifecycle works without repository infrastructure | each private host boundary | discard only the isolated snapshot after evidence is filed | no host network mutation or administrator action | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| O2 | every native GUI target | native accessibility API and screen reader available | GUI installed | agent resets to empty/no-provider and populated states | agent drives all focus, names, roles, loading, empty, failure, destructive confirmation and success states without pointer | AccessKit plus Narrator, VoiceOver or Orca output, app-only capture and backend oracle | complete operation is understandable and actionable; every control works or has a truthful disabled reason | private accessibility capture; no secret entry recorded | agent restores screen reader state | no owner action | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |
| C1 | each host after all its cells | none | every host cell has terminal result and evidence | agent enumerates Vadgr processes, temporary artifacts, devices, test credentials and isolated test state | agent stops only Vadgr test processes and removes only validated test artifacts, devices and credentials | final process/path/network/device inventory | no test process or artifact remains; source, evidence, configuration, normal owner state and unrelated files remain | private host cleanup record | none beyond this row | no owner action; scope is limited to runbook-created test items | not run: awaiting the final signed immutable candidate; run unaffected assertions only as development qualification |

## Per-OS results

| Part | Windows native | macOS | native Linux | WSL |
|---|---|---|---|---|
| H: protected owner boundaries | not run: final Windows candidate unavailable | not run: final macOS candidate unavailable | not run: final Linux candidate unavailable | Not-Needed: WSL has no native GUI or protected installer prompt |
| W: Windows cells | not run: unsigned development handoff is next | Not-Needed: Windows-only cells | Not-Needed: Windows-only cells | Not-Needed: Windows-only cells |
| M: macOS cells | Not-Needed: macOS-only cells | not run: final macOS candidate unavailable | Not-Needed: macOS-only cells | Not-Needed: macOS-only cells |
| L: native Linux cells | Not-Needed: native-Linux-only cells | Not-Needed: native-Linux-only cells | not run: final Linux candidate unavailable | Not-Needed: native-Linux-only cells |
| S: WSL cells | Not-Needed: WSL-only cells | Not-Needed: WSL-only cells | Not-Needed: WSL-only cells | not run: final WSL candidate unavailable |
| O: shared offline, accessibility and cleanup cells | not run: host qualification is incomplete | not run: host qualification is incomplete | not run: host qualification is incomplete | not run: host qualification is incomplete |

## Completion ledger

| host | cells | result |
|---|---:|---|
| Windows x64/arm64 | W01, W02, F01, W03 through W10, O1, O2, C1 | not run: unsigned development qualification is the next handoff; signed candidate unavailable |
| macOS Intel/Apple Silicon | M01, M02, F01, M03 through M06, O1, O2, C1 | not run: no host pass has started and signed candidate unavailable |
| Linux x86_64/aarch64 X11/Wayland | L01, L02, F01, L03 through L06, O1, O2, C1 | not run: no host pass has started and signed candidate unavailable |
| WSL x64/arm64 | S01 through S06, O1, C1 | not run: no host pass has started and final candidate unavailable |

Overall remains **not run** until every applicable row has execution evidence and
cleanup. CI, source inspection, an unsigned candidate or another host's result
cannot substitute for a cell.

## Windows development probe log

These observations are implementation feedback only. They are not cell results,
do not satisfy the completion ledger, and must be repeated against the immutable
candidate inside the private evidence boundary.

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
