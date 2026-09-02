# 0.5.0 - the product is installable: E2E runbook

> **Implementation:** `feature/0.5.0-distribution` at
> `3c5d82fc48a8b8557fb5c57e83a1c20d54efaa4d`; the PR resolves after the first
> target passes. **Private evidence PR:** resolve before the
> first live cell. Do not create a replacement PR.
>
> **Status: not started.** No cell below is a pass. Signing identities, reviewed
> terms, release public key, CUA 0.7.6, candidate artifacts and private evidence
> boundary are still prerequisites.

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

## Owner and external prerequisites

- Before any live cell: owner-approved Version 1.0 terms bytes; final legal
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

## Human-first cells

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions |
|---|---|---|---|---|---|---|---|---|---|---|
| W-H1 | Windows x64, then arm64 | owner at clean desktop; elevation available | no Vadgr product, state or launch entry | verify fixed artifact hashes | open setup, read terms, leave checkbox clear, choose decline | before/after product paths, HKCU Run, Start menu and state-root inventory | setup closes and creates nothing | private Windows boundary: screenshots plus inventories | delete download only after evidence is filed | no signing call; administrator may be requested only after acceptance |
| M-H1 | macOS Intel, then Apple Silicon | owner and administrator present | no Vadgr app, shim, state or login item | verify package signature, notarization and staple offline | open package, read terms, decline | before/after `/Applications`, shim, state and background-items inventory | Installer makes no mutation | private macOS boundary | delete download after filing | administrator must not be requested before acceptance |
| L-H1 | native Linux x86_64, then aarch64; X11 and Wayland | owner at graphical session | no Vadgr XDG generation, command, desktop or autostart entry | externally verify manifest signature and AppImage hash | open AppImage, read terms, leave checkbox clear, choose **Decline and close** | before/after XDG data/config, command and state inventories | no product or owner-state mutation | private Linux boundary | remove downloaded files after filing | no root; no package-manager action |
| S-H1 | WSL x64, then arm64 | owner at shell | no Vadgr generation, command or state | verify script attestation; set `RELEASE_DIR` to the immutable local asset directory | run `./install.sh --source "$RELEASE_DIR"`, read terms and enter anything except `ACCEPT 1.0` | before/after Linux roots plus Windows registry/network snapshots | no WSL or Windows mutation | private WSL boundary | remove temporary download directory | no GUI, elevation or Windows permission |
| M-H2 | both macOS architectures | owner controls privacy and Login Items | M-H1 complete; accepted signed package ready | keep terminal privacy grants absent | install, launch, approve login item, then deny and later grant Accessibility and Screen Recording to Vadgr Computer Use | System Settings identity, TCC behavior and CUA helper designated requirement | denial is truthful; grants attach to `com.montbrain.vadgr.cua`, not Terminal or Python | private macOS boundary; never export the TCC database | leave grants for M-I8 | Apple membership and administrator approval already named |
| W-H2 | Windows x64 and arm64 where supported | owner can approve elevation if Windows requests it | W-H1 complete | Smart App Control target ready | accept terms and drive setup through success; choose **Open Vadgr** | visible installer states, installed receipts, Startup Apps and console | real progress ends in success and ordinary launch opens the console | private Windows boundary | keep installation for W-I cells | one administrator approval; no provider cost |
| L-H2 | Linux X11 and Wayland | owner can answer optional dependency prompt | L-H1 complete | FUSE enabled for first pass | accept terms and choose Install | visible phases plus generation/current, desktop and autostart entries | verifying, staging, committing, registering launch, health check and complete appear in order | private Linux boundary | keep installation | dependency action requires separate approval and is recorded |
| F-H1 | each native GUI host | physical phone and bounded test provider | clean install healthy | enter provider secret through masked UI; do not capture it | connect provider, select default, pair by QR, then repeat by typed code | provider API state, pairing daemon lines, device transport rows | both pairing methods work; secret never appears in UI, logs or evidence | matching private host boundary | revoke test device and remove test credential after later cells | provider API usage may be billed; phone and camera permission required |

## Windows cells — Windows lead executes these only

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions |
|---|---|---|---|---|---|---|---|---|---|---|
| W-I1 | Windows x64, then arm64 | clean Smart App Control target | W-H2 not yet installed on fresh snapshot | obtain setup, MSI and manifest from immutable release | run `Get-AuthenticodeSignature` and SignTool verification on setup, MSI, cached Burn engine/uninstaller and every installed PE before and after install | valid chain, expected publisher and timestamp on each named file | every required vehicle and installed executable is valid; one unsigned layer fails | private Windows signature report | restore clean snapshot for W-H2 | no new signature operation |
| W-I2 | Windows x64/arm64 | none beyond W-H2 | signed install healthy | record `vadgr machine --json`, API machine and console | edit name, role prompt, autonomy mode, workspace and available grants in console; repeat selected edits with `vadgr config` | all three reads and database persistence after restart | one full machine snapshot; read-only fields rejected; no-op is idempotent | private Windows machine/API capture | restore original settings | none |
| W-I3 | Windows x64/arm64 | owner for phone actions | F-H1 paired | keep both transports available | inspect devices, transport details, connected state; cancel and confirm revoke | API device rows and live socket closure | safe fields only; cancel keeps device; confirm revokes and disconnects it | private Windows device capture | pair one device for later task | phone required |
| W-I4 | Windows x64/arm64 | provider account | default provider ready | start one harmless screenshot task | choose Restart Vadgr and observe progress; run task through bundled CUA | daemon PID/health transition and journal result | restart is truthful; task finishes using pinned CUA 0.7.6 and Python without system Python | private Windows daemon/journal capture | delete test run after filing | one bounded provider call; screen permission |
| W-I5 | Windows x64/arm64 | fault-injection snapshot | W-H2 healthy | prepare signed candidate with controlled failure at each named phase | inject download, verification, staging, dependency, daemon-stop, commit and health-check failure one at a time | prior setup launch, version and health after each attempt | every failure is specific and prior installation remains runnable | private Windows failure matrix | revert injection after each row | no signing retry; candidate only |
| W-I6 | Windows x64/arm64 | none | W-I5 complete | corrupt one package-owned file; keep retained signed source | choose Repair in Settings | MSI log, repaired hash and successful ordinary launch | repair restores only owned files and preserves owner state | private Windows repair capture | none | administrator only if Windows requests it |
| W-I7 | Windows x64/arm64 | signed previous and next candidate | current candidate healthy | ensure retained prior vehicle exists | update from local signed assets, then choose Roll back | signed manifests, versions, health and owner-state identity | update commits atomically; rollback selects verified prior version; identity/state stay equal | private Windows lifecycle capture | return to fixed test version | signed artifacts already produced; no signing call |
| W-I8 | Windows x64/arm64 | owner confirms destructive choice | W-I7 complete | hash owner state and record package paths | uninstall with preservation; reinstall; then uninstall again and type `DELETE OWNER DATA` | package inventory and owner-state identity after each operation | first uninstall preserves and reinstall finds state; second separate choice deletes only Vadgr state | private Windows uninstall capture | reinstall fixed candidate if later cells require it | administrator may be requested; destructive state deletion approved here |

## macOS cells — macOS owner executes these only

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions |
|---|---|---|---|---|---|---|---|---|---|---|
| M-I1 | Intel and Apple Silicon macOS | protected signed artifacts | M-H2 installed | network off after download | run `pkgutil`, `spctl`, `codesign` and stapler checks on package, app, CUA host and nested code | expected Team ID, hardened runtime, timestamp, staple and no `get-task-allow` | every layer verifies offline | private macOS signature report | none | no notarization call |
| M-I2 | both macOS architectures | owner | M-H2 grants active | record helper designated requirement | restart app, restart daemon, sign out/in and launch normally | CUA task and requirement string after each boundary | helper identity is byte-equal and grants survive all launches | private macOS identity capture | stay installed | Accessibility and Screen Recording |
| M-I3 | both macOS architectures | owner and provider | M-I2 complete | one paired phone | repeat W-I2 through W-I4 on macOS | CLI/API/console, device rows, health and journal | same shared behavior; platform launch uses SMAppService agent | private macOS functional capture | remove test run/device | provider billing and phone |
| M-I4 | both macOS architectures | signed next package | M-I3 complete | capture helper requirement and TCC result | update, repair, roll back, uninstall-preserve, reinstall, then explicit purge | signatures, requirement, health and state identities | prior install survives failure; rollback and repair work; MA2 closes across update without new grant | private macOS lifecycle/MA2 capture | remove product and grants after filing | administrator and privacy permissions |

## native Linux cells — Linux owner executes these only

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions |
|---|---|---|---|---|---|---|---|---|---|---|
| L-I1 | x86_64/aarch64, X11/Wayland | clean GUI hosts | L-H2 installed | keep FUSE; prepare extraction test | verify Minisign first, size/hash second; launch normally and with `--appimage-extract-and-run` | signature output, target match and both launches | both paths work; wrong key/signature/target/size/hash fails before XDG mutation | private Linux integrity capture | delete tampered copies | none |
| L-I2 | same matrix | provider and phone | L-I1 complete | one provider/default and paired device | repeat W-I2 through W-I4 | CLI/API/console, transport and journal | shared console/backend behavior matches Windows | private Linux functional capture | remove run/device | bounded provider call and phone |
| L-I3 | same matrix | fault-injection host | L-I2 complete | signed local previous/next generations | inject every W-I5 failure; repair, update and roll back | `current` link, version receipts, health and state identity | atomic link restores prior generation; repair uses retained verified source | private Linux lifecycle capture | select fixed generation | no root |
| L-I4 | same matrix | owner confirms purge | L-I3 complete | record XDG and state roots | uninstall-preserve/reinstall; then typed purge | exact paths and state identity | only package/XDG entries removed first; state found on reinstall; purge deletes exact state root | private Linux uninstall capture | remove all test artifacts | destructive state deletion approved here |

## WSL cells — WSL owner executes these only

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions |
|---|---|---|---|---|---|---|---|---|---|---|
| S-I1 | WSL x64/arm64 | clean distributions | S-H1 complete | local immutable release in `$RELEASE_DIR`; network blocked | run `install.sh --source "$RELEASE_DIR" --accept-terms 1.0` | verifier output, archive inventory, version/target/pins and health | CLI-only install succeeds with CUA 0.7.6/Python pin and no system Python/toolchain | private WSL install capture | keep installation | no elevation or GUI |
| S-I2 | WSL x64/arm64 | none | S-I1 clean snapshot | tampered copies | independently alter verifier, public key build, manifest, signature, target, size, hash, traversal and escaping link | exit and before/after WSL/Windows inventories | every case fails before install mutation; Windows registry, DNS, firewall, VPN and files unchanged | private WSL negative matrix | delete tampered files | none |
| S-I3 | WSL x64/arm64 | provider account | S-I1 healthy | provider configured securely | run one screenshot task through bundled CUA; compare CLI/API machine config after edits | journal and pin records | task succeeds; machine store persists; no GUI/autostart/service exists | private WSL functional capture | remove run and provider credential | bounded provider call |
| S-I4 | WSL x64/arm64 | fault-injection distribution | S-I3 complete | retained previous/next archives | inject failures, update, repair and rollback through `install.sh` | `current`, receipts, health and state identity | prior generation remains runnable and rollback is verified/local | private WSL lifecycle capture | restore fixed version | none |
| S-I5 | WSL x64/arm64 | owner confirms purge | S-I4 complete | record state identity | uninstall-preserve/reinstall; then `--delete-owner-state` and type confirmation | exact Linux roots and Windows no-change snapshot | owner state survives first cycle; separate purge removes only WSL Vadgr state | private WSL uninstall capture | remove test assets | destructive WSL state deletion approved here |

## Shared offline and cleanup cells

| cell | operating system and architecture | owner/environment requirements | precondition | setup | exact action | oracle | expected result | evidence boundary | cleanup | cost, accounts, devices and permissions |
|---|---|---|---|---|---|---|---|---|---|---|
| O1 | every installed target | network controls approved | target functional cells pass | block GitHub, MONTBRAIN and publisher-controlled hosts; leave configured provider/transport dependencies isolated to their own cells | launch CLI/console, open legal notices, restart, repair, roll back and uninstall | process/health, offline files and package receipts | installed product lifecycle works without repository infrastructure | each private host boundary | restore network rules exactly | administrator only for temporary network rule where required |
| O2 | every native GUI target | keyboard and native screen reader | GUI installed | reset to empty/no-provider and populated states | drive all focus, names, roles, loading, empty, failure, destructive confirmation and success states without pointer | AccessKit plus Narrator, VoiceOver or Orca speech | complete operation is understandable and actionable | private accessibility capture; no secret entry recorded | restore screen reader state | accessibility tool and owner |
| C1 | each host after all its cells | host owner | every host cell has terminal result and evidence | enumerate Vadgr processes, temporary artifacts, devices, credentials and test state | stop only Vadgr test processes; remove only test artifacts and temporary grants/rules | final process/path/network/device inventory | no test process or artifact remains; source, evidence, configuration, owner state and unrelated files remain | private host cleanup record | none beyond this row | owner approves removal of test credential/device |

## Completion ledger

| host | cells | result |
|---|---:|---|
| Windows x64/arm64 | W-H1, W-H2, F-H1, W-I1–W-I8, O1, O2, C1 | not run |
| macOS Intel/Apple Silicon | M-H1, M-H2, F-H1, M-I1–M-I4, O1, O2, C1 | not run |
| Linux x86_64/aarch64 X11/Wayland | L-H1, L-H2, F-H1, L-I1–L-I4, O1, O2, C1 | not run |
| WSL x64/arm64 | S-H1, S-I1–S-I5, O1, C1 | not run |

Overall remains **not run** until every applicable row has execution evidence and
cleanup. CI, source inspection, an unsigned candidate or another host's result
cannot substitute for a cell.
