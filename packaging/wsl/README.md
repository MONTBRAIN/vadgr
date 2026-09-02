# WSL package

WSL receives `install.sh` and one immutable target archive. It has no GUI,
desktop entry, autostart entry, or service. The script downloads a small static
manifest verifier whose exact per-architecture hash is pinned in the script,
verifies the Minisign signature before trusting artifact metadata, validates
archive paths and links, and only then extracts into temporary storage.

The verifier hashes remain `UNCONFIGURED` until the reviewed verifier builds and
release public key exist. That state fails closed. The release process replaces
both values through review; it never downloads or creates a signing key.
