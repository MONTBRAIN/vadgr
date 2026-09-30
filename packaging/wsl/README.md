# WSL package

WSL receives `install.sh` and one immutable target archive. It has no GUI,
desktop entry, autostart entry, or service. The script downloads a small static
manifest verifier whose exact per-architecture hash is pinned in the script,
verifies the keyless manifest bundle under a pinned root and workflow policy
before trusting artifact metadata, validates
archive paths and links, and only then extracts into temporary storage.

The verifier hashes remain `UNCONFIGURED` until the reviewed verifier builds
are pinned in `install.sh`. That state fails closed. The published verifier
carries its authenticated trust root; no permanent release key exists.
