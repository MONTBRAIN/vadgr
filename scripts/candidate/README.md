# Held Windows candidate tools

The manual candidate workflow runs only from the default branch. It builds an
exact pushed source commit without signing credentials and validates the uploaded
bytes independently. The source branch does not supply signing scripts or WiX
projects to the protected signer.

CI also runs on pushes to `feature/0.5.0-distribution`, so that exact source
commit can earn required checks before a pull request exists. Other feature
branches retain the pull-request trigger. This adds runner use, not secret access.

The authorization environment approves the exact artifact and quota. A separate
job consumes that authorization with an immutable Git claim. The Windows signing
environment then approves one signing attempt. Failed or uncertain attempts stay
spent. Recovery needs a reconciled quota and a new explicit authorization.

`build-windows.ps1` runs only on a secret-free source-build runner.
`package-windows.ps1` reads compiled payloads as data and uses trusted WiX
authoring. It never compiles or executes a candidate DLL.
`hold-windows.ps1` verifies the final signatures and writes the held inventory.
`record.py` extracts one bounded JSON record without extracting archive paths.

The output is an unpublished Windows candidate. Offline manifest signing and
native installer tests remain required. This workflow creates no release and
does not change any existing tag or environment protections.
