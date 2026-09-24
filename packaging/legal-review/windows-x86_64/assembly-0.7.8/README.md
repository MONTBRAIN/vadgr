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
