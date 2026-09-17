# First boundary observations

Build: `3d8bfc9614e1c1ea43986a878ebfde44e2407aad`.

Native archive cases failed before the intended guard due to an import defect.
They are failures, not accepted unsafe-archive refusals. Rerun after repair.
Other case verdicts still require their filesystem oracles.

## B01-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/fixture GITHUB_RUN_ATTEMPT=1 python3 scripts/candidate_policy.py preflight --source-root . --branch feature/fixture --source-sha 3d8bfc9614e1c1ea43986a878ebfde44e2407aad --version 0.5.0 --candidate-id v0.5.0-rc-1 --architecture x64 --out FIXTURE/preflight.json --materialize FIXTURE/materialized
```

Exit: 1.

```text
CANDIDATE REFUSED: trusted workflow identity is invalid
```

## B01-Windows

Command:

```text
$base="CHECKOUT"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/fixture"; $env:GITHUB_RUN_ATTEMPT="1"; & python (Join-Path $base "scripts\candidate_policy.py") preflight --source-root $base --branch feature/fixture --source-sha 3d8bfc9614e1c1ea43986a878ebfde44e2407aad --version 0.5.0 --candidate-id v0.5.0-rc-1 --architecture x64 --out "NATIVE-TEMP\fixtures\preflight.json" --materialize "NATIVE-TEMP\fixtures\materialized"; exit $LASTEXITCODE
```

Exit: 1.

```text
CANDIDATE REFUSED: trusted workflow identity is invalid
```

## B02-traversal-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/master GITHUB_RUN_ATTEMPT=1 GITHUB_RUN_ID=1 GITHUB_SHA=3d8bfc9614e1c1ea43986a878ebfde44e2407aad python3 scripts/candidate_artifacts.py extract-verified --archive FIXTURE/traversal.zip --authorization FIXTURE/authorization.json --extract FIXTURE/traversal-output
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate has unsafe path
```

## B02-traversal-Windows

Command:

```text
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/master"; $env:GITHUB_RUN_ATTEMPT="1"; $env:GITHUB_RUN_ID="1"; $env:GITHUB_SHA="3d8bfc9614e1c1ea43986a878ebfde44e2407aad"; & python (Join-Path $base "scripts\candidate_artifacts.py") extract-verified --archive (Join-Path $fixture "traversal.zip") --authorization (Join-Path $fixture "authorization.json") --extract (Join-Path $fixture "traversal-output"); exit $LASTEXITCODE
```

Exit: 1.

```text
Traceback (most recent call last):
  File "CHECKOUT\scripts\candidate_artifacts.py", line 18, in <module>
    from scripts import candidate_policy
ImportError: cannot import name 'candidate_policy' from 'scripts' (unknown location)
```

## B02-symlink-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/master GITHUB_RUN_ATTEMPT=1 GITHUB_RUN_ID=1 GITHUB_SHA=3d8bfc9614e1c1ea43986a878ebfde44e2407aad python3 scripts/candidate_artifacts.py extract-verified --archive FIXTURE/symlink.zip --authorization FIXTURE/authorization.json --extract FIXTURE/symlink-output
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate contains a link or special file
```

## B02-symlink-Windows

Command:

```text
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/master"; $env:GITHUB_RUN_ATTEMPT="1"; $env:GITHUB_RUN_ID="1"; $env:GITHUB_SHA="3d8bfc9614e1c1ea43986a878ebfde44e2407aad"; & python (Join-Path $base "scripts\candidate_artifacts.py") extract-verified --archive (Join-Path $fixture "symlink.zip") --authorization (Join-Path $fixture "authorization.json") --extract (Join-Path $fixture "symlink-output"); exit $LASTEXITCODE
```

Exit: 1.

```text
Traceback (most recent call last):
  File "CHECKOUT\scripts\candidate_artifacts.py", line 18, in <module>
    from scripts import candidate_policy
ImportError: cannot import name 'candidate_policy' from 'scripts' (unknown location)
```

## B02-case-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/master GITHUB_RUN_ATTEMPT=1 GITHUB_RUN_ID=1 GITHUB_SHA=3d8bfc9614e1c1ea43986a878ebfde44e2407aad python3 scripts/candidate_artifacts.py extract-verified --archive FIXTURE/case.zip --authorization FIXTURE/authorization.json --extract FIXTURE/case-output
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate has duplicate or case-colliding path
```

## B02-case-Windows

Command:

```text
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/master"; $env:GITHUB_RUN_ATTEMPT="1"; $env:GITHUB_RUN_ID="1"; $env:GITHUB_SHA="3d8bfc9614e1c1ea43986a878ebfde44e2407aad"; & python (Join-Path $base "scripts\candidate_artifacts.py") extract-verified --archive (Join-Path $fixture "case.zip") --authorization (Join-Path $fixture "authorization.json") --extract (Join-Path $fixture "case-output"); exit $LASTEXITCODE
```

Exit: 1.

```text
Traceback (most recent call last):
  File "CHECKOUT\scripts\candidate_artifacts.py", line 18, in <module>
    from scripts import candidate_policy
ImportError: cannot import name 'candidate_policy' from 'scripts' (unknown location)
```

## B02-reserved-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/master GITHUB_RUN_ATTEMPT=1 GITHUB_RUN_ID=1 GITHUB_SHA=3d8bfc9614e1c1ea43986a878ebfde44e2407aad python3 scripts/candidate_artifacts.py extract-verified --archive FIXTURE/reserved.zip --authorization FIXTURE/authorization.json --extract FIXTURE/reserved-output
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate has unsafe path
```

## B02-reserved-Windows

Command:

```text
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/master"; $env:GITHUB_RUN_ATTEMPT="1"; $env:GITHUB_RUN_ID="1"; $env:GITHUB_SHA="3d8bfc9614e1c1ea43986a878ebfde44e2407aad"; & python (Join-Path $base "scripts\candidate_artifacts.py") extract-verified --archive (Join-Path $fixture "reserved.zip") --authorization (Join-Path $fixture "authorization.json") --extract (Join-Path $fixture "reserved-output"); exit $LASTEXITCODE
```

Exit: 1.

```text
Traceback (most recent call last):
  File "CHECKOUT\scripts\candidate_artifacts.py", line 18, in <module>
    from scripts import candidate_policy
ImportError: cannot import name 'candidate_policy' from 'scripts' (unknown location)
```

## B03-record-WSL

Command:

```text
python3 scripts/candidate/record.py --archive FIXTURE/record.zip --name authorization.json --out FIXTURE/record-output.json
```

Exit: 0.

```text
Trusted record extracted; no archive paths materialized.
```

## B03-record-Windows

Command:

```text
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures"; & python (Join-Path $base "scripts\candidate\record.py") --archive (Join-Path $fixture "record.zip") --name authorization.json --out (Join-Path $fixture "record-output.json"); exit $LASTEXITCODE
```

Exit: 0.

```text
Trusted record extracted; no archive paths materialized.
```

## B03-extra-WSL

Command:

```text
python3 scripts/candidate/record.py --archive FIXTURE/extra.zip --name authorization.json --out FIXTURE/extra-output.json
```

Exit: 1.

```text
Traceback (most recent call last):
  File "CHECKOUT/scripts/candidate/record.py", line 31, in <module>
    extract(arguments.archive, arguments.name, arguments.out)
  File "CHECKOUT/scripts/candidate/record.py", line 14, in extract
    raise ValueError("record artifact must contain exactly its declared record")
ValueError: record artifact must contain exactly its declared record
```

## B03-extra-Windows

Command:

```text
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures"; & python (Join-Path $base "scripts\candidate\record.py") --archive (Join-Path $fixture "extra.zip") --name authorization.json --out (Join-Path $fixture "extra-output.json"); exit $LASTEXITCODE
```

Exit: 1.

```text
Traceback (most recent call last):
  File "CHECKOUT\scripts\candidate\record.py", line 31, in <module>
    extract(arguments.archive, arguments.name, arguments.out)
  File "CHECKOUT\scripts\candidate\record.py", line 14, in extract
    raise ValueError("record artifact must contain exactly its declared record")
ValueError: record artifact must contain exactly its declared record
```

## B04-Windows

Command:

```text
$ErrorActionPreference="Stop"; $env:GITHUB_ACTIONS="true"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF_TYPE="branch"; $env:GITHUB_REF="refs/heads/fixture"; $env:GITHUB_RUN_ATTEMPT="1"; & "NATIVE-TEMP\signing\release.ps1" -Mode sign -Root "NATIVE-TEMP\fixtures\B04-Windows"
```

Exit: 1.

```text
Signing is restricted to the first attempt of an approved default-branch candidate.
At NATIVE-TEMP\signing\release.ps1:89 char:5
+     throw 'Signing is restricted to the first attempt of an approved  ...
+     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : OperationStopped: (Signing is rest...anch candidate.:String) [], RuntimeException
    + FullyQualifiedErrorId : Signing is restricted to the first attempt of an approved default-branch candidate.
```

## B05-Windows

Command:

```text
$ErrorActionPreference="Stop"; $env:GITHUB_ACTIONS="true"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF_TYPE="branch"; $env:GITHUB_REF="refs/heads/master"; $env:GITHUB_RUN_ATTEMPT="2"; & "NATIVE-TEMP\signing\release.ps1" -Mode sign -Root "NATIVE-TEMP\fixtures\B05-Windows"
```

Exit: 1.

```text
Signing is restricted to the first attempt of an approved default-branch candidate.
At NATIVE-TEMP\signing\release.ps1:89 char:5
+     throw 'Signing is restricted to the first attempt of an approved  ...
+     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : OperationStopped: (Signing is rest...anch candidate.:String) [], RuntimeException
    + FullyQualifiedErrorId : Signing is restricted to the first attempt of an approved default-branch candidate.
```


