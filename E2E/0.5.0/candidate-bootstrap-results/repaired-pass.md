# Repaired boundary observations

Build: `5cd8065676cfd9faab674ff1a5a2c49718a97500`.

B01-B05 were repeated against this pushed commit. B06 used the same signing
scripts, copied earlier and independently hash-compared with this commit.
B06 downloaded the pinned vendor archive, compiled the real launcher with
Temurin 17.0.20+8, and ran its missing-file self-test. No live account was used.

## B01-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/fixture GITHUB_RUN_ATTEMPT=1 python3 scripts/candidate_policy.py preflight --source-root . --branch feature/fixture --source-sha 5cd8065676cfd9faab674ff1a5a2c49718a97500 --version 0.5.0 --candidate-id v0.5.0-rc-1 --architecture x64 --out FIXTURE/preflight.json --materialize FIXTURE/materialized
```

Exit: 1.

```text
CANDIDATE REFUSED: trusted workflow identity is invalid
```

## B01-Windows

Command:

```text
$base="CHECKOUT"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/fixture"; $env:GITHUB_RUN_ATTEMPT="1"; & python (Join-Path $base "scripts\candidate_policy.py") preflight --source-root $base --branch feature/fixture --source-sha 5cd8065676cfd9faab674ff1a5a2c49718a97500 --version 0.5.0 --candidate-id v0.5.0-rc-1 --architecture x64 --out "NATIVE-TEMP\fixtures-5cd8065\preflight.json" --materialize "NATIVE-TEMP\fixtures-5cd8065\materialized"; exit $LASTEXITCODE
```

Exit: 1.

```text
CANDIDATE REFUSED: trusted workflow identity is invalid
```

## B02-traversal-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/master GITHUB_RUN_ATTEMPT=1 GITHUB_RUN_ID=1 GITHUB_SHA=5cd8065676cfd9faab674ff1a5a2c49718a97500 python3 scripts/candidate_artifacts.py extract-verified --archive FIXTURE/traversal.zip --authorization FIXTURE/authorization.json --extract FIXTURE/traversal-output
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate has unsafe path
```

## B02-traversal-Windows

Command:

```text
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures-5cd8065"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/master"; $env:GITHUB_RUN_ATTEMPT="1"; $env:GITHUB_RUN_ID="1"; $env:GITHUB_SHA="5cd8065676cfd9faab674ff1a5a2c49718a97500"; & python (Join-Path $base "scripts\candidate_artifacts.py") extract-verified --archive (Join-Path $fixture "traversal.zip") --authorization (Join-Path $fixture "authorization.json") --extract (Join-Path $fixture "traversal-output"); exit $LASTEXITCODE
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate has unsafe path
```

## B02-symlink-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/master GITHUB_RUN_ATTEMPT=1 GITHUB_RUN_ID=1 GITHUB_SHA=5cd8065676cfd9faab674ff1a5a2c49718a97500 python3 scripts/candidate_artifacts.py extract-verified --archive FIXTURE/symlink.zip --authorization FIXTURE/authorization.json --extract FIXTURE/symlink-output
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate contains a link or special file
```

## B02-symlink-Windows

Command:

```text
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures-5cd8065"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/master"; $env:GITHUB_RUN_ATTEMPT="1"; $env:GITHUB_RUN_ID="1"; $env:GITHUB_SHA="5cd8065676cfd9faab674ff1a5a2c49718a97500"; & python (Join-Path $base "scripts\candidate_artifacts.py") extract-verified --archive (Join-Path $fixture "symlink.zip") --authorization (Join-Path $fixture "authorization.json") --extract (Join-Path $fixture "symlink-output"); exit $LASTEXITCODE
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate contains a link or special file
```

## B02-case-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/master GITHUB_RUN_ATTEMPT=1 GITHUB_RUN_ID=1 GITHUB_SHA=5cd8065676cfd9faab674ff1a5a2c49718a97500 python3 scripts/candidate_artifacts.py extract-verified --archive FIXTURE/case.zip --authorization FIXTURE/authorization.json --extract FIXTURE/case-output
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate has duplicate or case-colliding path
```

## B02-case-Windows

Command:

```text
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures-5cd8065"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/master"; $env:GITHUB_RUN_ATTEMPT="1"; $env:GITHUB_RUN_ID="1"; $env:GITHUB_SHA="5cd8065676cfd9faab674ff1a5a2c49718a97500"; & python (Join-Path $base "scripts\candidate_artifacts.py") extract-verified --archive (Join-Path $fixture "case.zip") --authorization (Join-Path $fixture "authorization.json") --extract (Join-Path $fixture "case-output"); exit $LASTEXITCODE
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate has duplicate or case-colliding path
```

## B02-reserved-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/master GITHUB_RUN_ATTEMPT=1 GITHUB_RUN_ID=1 GITHUB_SHA=5cd8065676cfd9faab674ff1a5a2c49718a97500 python3 scripts/candidate_artifacts.py extract-verified --archive FIXTURE/reserved.zip --authorization FIXTURE/authorization.json --extract FIXTURE/reserved-output
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate has unsafe path
```

## B02-reserved-Windows

Command:

```text
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures-5cd8065"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/master"; $env:GITHUB_RUN_ATTEMPT="1"; $env:GITHUB_RUN_ID="1"; $env:GITHUB_SHA="5cd8065676cfd9faab674ff1a5a2c49718a97500"; & python (Join-Path $base "scripts\candidate_artifacts.py") extract-verified --archive (Join-Path $fixture "reserved.zip") --authorization (Join-Path $fixture "authorization.json") --extract (Join-Path $fixture "reserved-output"); exit $LASTEXITCODE
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate has unsafe path
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
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures-5cd8065"; & python (Join-Path $base "scripts\candidate\record.py") --archive (Join-Path $fixture "record.zip") --name authorization.json --out (Join-Path $fixture "record-output.json"); exit $LASTEXITCODE
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
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures-5cd8065"; & python (Join-Path $base "scripts\candidate\record.py") --archive (Join-Path $fixture "extra.zip") --name authorization.json --out (Join-Path $fixture "extra-output.json"); exit $LASTEXITCODE
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

## B06-Windows

Command:

```text
$ErrorActionPreference="Stop"; $env:PATH="NATIVE-TEMP\jdk-ci\jdk-17.0.20+8\bin;"+$env:PATH; & "NATIVE-TEMP\signing\release.ps1" -Mode prepare -Budget 5 -Root "NATIVE-TEMP\B06"; if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
```

Exit: 0.

```text
Dummy credential suppression: PASS; vendor missing-file refusal verified.
```

## oracle-WSL

Command:

```text
test ! -e FIXTURE/materialized && test ! -e FIXTURE/preflight.json && test ! -e FIXTURE/traversal-output && test ! -e FIXTURE/symlink-output && test ! -e FIXTURE/case-output && test ! -e FIXTURE/reserved-output && test ! -e OUTSIDE-FIXTURE && test ! -e FIXTURE/extra-output.json && cmp FIXTURE/authorization.json FIXTURE/record-output.json && sha256sum FIXTURE/*.zip FIXTURE/authorization.json FIXTURE/record-output.json
```

Exit: 0.

```text
5ccb5d4cb3f2982d68f310957f277caeba5c98fe4dbf61c0b54b912b223a6248  FIXTURE/case.zip
9902c212861a8c06f4009aeb6467e80f23dc7b1190aa54645a78d2fed46bc6ea  FIXTURE/extra.zip
acfb85f1b04a7b1175fbdc52c0498ee7146a74c7005c9589b1cfeb26ff289806  FIXTURE/record.zip
5936dfe3b004dafaf730f589c90bf18199ed0c0a4f0713f7a5772895dfab4f00  FIXTURE/reserved.zip
c52e29dba90f959ef5fc8eee10995717b123895e7c63db2438c4943db6e186c9  FIXTURE/symlink.zip
2ea7b826689ffd66f2db2de03187804d3a7569add03f351f66530d4c92033fd8  FIXTURE/traversal.zip
b58fbd24f35bc1e6e6016a3ec1fd943c72ce4eda47f79c3192918e4b0693f1a9  FIXTURE/authorization.json
b58fbd24f35bc1e6e6016a3ec1fd943c72ce4eda47f79c3192918e4b0693f1a9  FIXTURE/record-output.json
```

## oracle-Windows

Command:

```text
$ErrorActionPreference="Stop"; $fixture="NATIVE-TEMP\fixtures-5cd8065"; foreach($name in @("materialized","preflight.json","traversal-output","symlink-output","case-output","reserved-output","extra-output.json")){if(Test-Path (Join-Path $fixture $name)){throw "Unexpected output: $name"}}; if(Test-Path "NATIVE-TEMP\outside.txt"){throw "Escaped output"}; $hashes=Get-Content (Join-Path $fixture "fixture-hashes.json") -Raw | ConvertFrom-Json; foreach($property in $hashes.PSObject.Properties){if((Get-FileHash (Join-Path $fixture $property.Name)).Hash.ToLower() -ne $property.Value){throw "Fixture changed"}}; if((Get-FileHash (Join-Path $fixture "authorization.json")).Hash -ne (Get-FileHash (Join-Path $fixture "record-output.json")).Hash){throw "Record changed"}; foreach($name in @("B04-Windows","B05-Windows")){if(Test-Path "NATIVE-TEMP\fixtures\$name"){throw "Signer wrote output"}}; Write-Output "PASS: fixtures unchanged; no refused output; no escaped path; exact record copy; no signing ledger."
```

Exit: 0.

```text
PASS: fixtures unchanged; no refused output; no escaped path; exact record copy; no signing ledger.
```

## oracle-B06

Command:

```text
$ErrorActionPreference="Stop"; $root="NATIVE-TEMP\B06"; if(Test-Path (Join-Path $root "logs")){throw "Vendor logs exist"}; if(Test-Path (Join-Path $root "missing-smoke-input.exe")){throw "Missing-file guard compromised"}; $ledger=Get-Content (Join-Path $root "ledger.json") -Raw|ConvertFrom-Json; if($ledger.budget -ne 5 -or @($ledger.attempts).Count -ne 0){throw "Unexpected ledger"}; $jar=(Get-FileHash (Join-Path $root "code_sign_tool-1.3.3.jar")).Hash; if($jar -ne "CAA356347AA64BA04666545D548DAD87211C9AA960F16DB8797A880A67BA91D1"){throw "JAR changed"}; $source="CHECKOUT\scripts\signing"; foreach($name in @("release.ps1","CodeSignRunner.java","log4j2-off.xml")){if((Get-FileHash (Join-Path $source $name)).Hash -ne (Get-FileHash (Join-Path "NATIVE-TEMP\signing" $name)).Hash){throw "Source copy differs"}}; & "NATIVE-TEMP\jdk-ci\jdk-17.0.20+8\bin\java.exe" -version; if($LASTEXITCODE -ne 0){throw "Java version unavailable"}; Write-Output "PASS: exact source copy; pinned JAR; no vendor logs; missing input absent; zero signing attempts."
```

Exit: 0.

```text
openjdk version "17.0.20" 2026-07-21
OpenJDK Runtime Environment Temurin-17.0.20+8 (build 17.0.20+8)
OpenJDK 64-Bit Server VM Temurin-17.0.20+8 (build 17.0.20+8, mixed mode, sharing)
PASS: exact source copy; pinned JAR; no vendor logs; missing input absent; zero signing attempts.
```


