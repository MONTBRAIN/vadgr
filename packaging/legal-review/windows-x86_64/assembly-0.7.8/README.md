# Unsigned Windows x64 assembly observation

This is not a package-input inventory or approval. It records one isolated,
credential-free assembly of the exact 40-wheel CUA 0.7.8 closure. The assembly
used the development-profile CLI with the committed release lock and manifest.
The observed source file and assembler hashes identify local cleanup changes
after the recorded base commit. It is not a release build or an installed E2E
pass.

The first assembly retained four foreign pip/distlib launcher templates and
failed the independent architecture check. It also retained Python debug files.
The corrected assembly removes Python debug, cache and test material plus
foreign launcher templates before sealing the inventory. The private runtime
probe and the independent check of 128 loose native files then passed.

The broker ZIP still contains 23 PE members. Of these, 21 have no embedded
Authenticode certificate table. The observation checks certificate presence,
not cryptographic validity or publisher trust. A loose-file architecture pass
cannot establish the trust of a compressed executable.

The checked-in manifest and inventory preserve this refusal, not admission.
The exact Windows x64 legal packet must be regenerated from the corrected CUA
profile. Nested signing, final native verification and the owner's exact legal
review remain required. No closure, candidate admission or signing approval is
granted here. ARM64 and macOS package inputs remain absent and owed.

## Failed CI retained

`failed-ci-runs.json` records the failed jobs and exact source revision from
runs 35962297116 and 35962297141. The ordinary Linux and macOS builds and both
verifier builds stopped at the assertion that a target lock and the global
wheel manifest must arrive together. Ordinary compilation now permits a target
whose reviewed lock is absent. Release compilation and payload assembly still
refuse that target.

The Windows installer job invoked the retired source installer without the
required closed wheelhouse. The source entry point now refuses without changing
owner state and directs users to the graphical installer. The Unix clean-install
jobs refused missing target locks during preparation. CI now checks that refusal
explicitly and records clean installation as not run. This is not an installed
product pass and does not qualify those targets for a candidate.

`powershell-probe-failure.json` retains the subsequent CI failures at source
`a081a6caf2e55b6d18ff653d7a9c610d7f8620fa`. PowerShell 7.6.5 rewrote
`StartupProfileData-NonInteractive` in the isolated profile, even after a
file-mode warmup. The exact runner version reproduced this twice locally.
The probe now separates the shell's profile from the installer's profile.
Only content changes to the two exact shell startup cache paths are permitted;
unknown paths, cache removal and every installer-profile change remain checked.

The Rust missing-lock refusal fixture also failed because the runner exposed
its temporary directory through a junction. An isolated local junction
reproduced the failure. Canonicalizing that synthetic fixture fixed it without
changing the production refusal of linked install roots.
