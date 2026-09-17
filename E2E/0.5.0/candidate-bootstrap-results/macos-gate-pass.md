# Required macOS gate repair: boundary observations

Build: `1c0901dbd47dfa9f156bb67ac03235cea32254d5`.

B01-B06 repeated after adding the required macOS credential gate matrix entry.
Candidate executables and signing sources are unchanged from the previous pass.
B06 reuses the independently verified native JDK, JAR and compiled launcher.
The first direct Java command had incorrect PowerShell argument quoting; the
corrected command passed. Both outputs are retained. Zero signing attempts.

Local gates: 200 Python tests passed, 2 skipped, 8 subtests passed. Cargo tests,
clippy with all targets/features, formatting, and secret scanning passed.

## B01-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/fixture GITHUB_RUN_ATTEMPT=1 python3 scripts/candidate_policy.py preflight --source-root . --branch feature/fixture --source-sha 1c0901dbd47dfa9f156bb67ac03235cea32254d5 --version 0.5.0 --candidate-id v0.5.0-rc-1 --architecture x64 --out FIXTURE/preflight.json --materialize FIXTURE/materialized
```

Exit: 1.

```text
CANDIDATE REFUSED: trusted workflow identity is invalid
```

## B01-Windows

Command:

```text
$base="CHECKOUT"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/fixture"; $env:GITHUB_RUN_ATTEMPT="1"; & python (Join-Path $base "scripts\candidate_policy.py") preflight --source-root $base --branch feature/fixture --source-sha 1c0901dbd47dfa9f156bb67ac03235cea32254d5 --version 0.5.0 --candidate-id v0.5.0-rc-1 --architecture x64 --out "NATIVE-TEMP\fixtures-1c0901d\preflight.json" --materialize "NATIVE-TEMP\fixtures-1c0901d\materialized"; exit $LASTEXITCODE
```

Exit: 1.

```text
CANDIDATE REFUSED: trusted workflow identity is invalid
```

## B02-traversal-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/master GITHUB_RUN_ATTEMPT=1 GITHUB_RUN_ID=1 GITHUB_SHA=1c0901dbd47dfa9f156bb67ac03235cea32254d5 python3 scripts/candidate_artifacts.py extract-verified --archive FIXTURE/traversal.zip --authorization FIXTURE/authorization.json --extract FIXTURE/traversal-output
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate has unsafe path
```

## B02-traversal-Windows

Command:

```text
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures-1c0901d"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/master"; $env:GITHUB_RUN_ATTEMPT="1"; $env:GITHUB_RUN_ID="1"; $env:GITHUB_SHA="1c0901dbd47dfa9f156bb67ac03235cea32254d5"; & python (Join-Path $base "scripts\candidate_artifacts.py") extract-verified --archive (Join-Path $fixture "traversal.zip") --authorization (Join-Path $fixture "authorization.json") --extract (Join-Path $fixture "traversal-output"); exit $LASTEXITCODE
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate has unsafe path
```

## B02-symlink-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/master GITHUB_RUN_ATTEMPT=1 GITHUB_RUN_ID=1 GITHUB_SHA=1c0901dbd47dfa9f156bb67ac03235cea32254d5 python3 scripts/candidate_artifacts.py extract-verified --archive FIXTURE/symlink.zip --authorization FIXTURE/authorization.json --extract FIXTURE/symlink-output
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate contains a link or special file
```

## B02-symlink-Windows

Command:

```text
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures-1c0901d"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/master"; $env:GITHUB_RUN_ATTEMPT="1"; $env:GITHUB_RUN_ID="1"; $env:GITHUB_SHA="1c0901dbd47dfa9f156bb67ac03235cea32254d5"; & python (Join-Path $base "scripts\candidate_artifacts.py") extract-verified --archive (Join-Path $fixture "symlink.zip") --authorization (Join-Path $fixture "authorization.json") --extract (Join-Path $fixture "symlink-output"); exit $LASTEXITCODE
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate contains a link or special file
```

## B02-case-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/master GITHUB_RUN_ATTEMPT=1 GITHUB_RUN_ID=1 GITHUB_SHA=1c0901dbd47dfa9f156bb67ac03235cea32254d5 python3 scripts/candidate_artifacts.py extract-verified --archive FIXTURE/case.zip --authorization FIXTURE/authorization.json --extract FIXTURE/case-output
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate has duplicate or case-colliding path
```

## B02-case-Windows

Command:

```text
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures-1c0901d"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/master"; $env:GITHUB_RUN_ATTEMPT="1"; $env:GITHUB_RUN_ID="1"; $env:GITHUB_SHA="1c0901dbd47dfa9f156bb67ac03235cea32254d5"; & python (Join-Path $base "scripts\candidate_artifacts.py") extract-verified --archive (Join-Path $fixture "case.zip") --authorization (Join-Path $fixture "authorization.json") --extract (Join-Path $fixture "case-output"); exit $LASTEXITCODE
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate has duplicate or case-colliding path
```

## B02-reserved-WSL

Command:

```text
env GITHUB_REPOSITORY=MONTBRAIN/vadgr GITHUB_REF=refs/heads/master GITHUB_RUN_ATTEMPT=1 GITHUB_RUN_ID=1 GITHUB_SHA=1c0901dbd47dfa9f156bb67ac03235cea32254d5 python3 scripts/candidate_artifacts.py extract-verified --archive FIXTURE/reserved.zip --authorization FIXTURE/authorization.json --extract FIXTURE/reserved-output
```

Exit: 1.

```text
CANDIDATE ARTIFACT REFUSED: candidate has unsafe path
```

## B02-reserved-Windows

Command:

```text
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures-1c0901d"; $env:GITHUB_REPOSITORY="MONTBRAIN/vadgr"; $env:GITHUB_REF="refs/heads/master"; $env:GITHUB_RUN_ATTEMPT="1"; $env:GITHUB_RUN_ID="1"; $env:GITHUB_SHA="1c0901dbd47dfa9f156bb67ac03235cea32254d5"; & python (Join-Path $base "scripts\candidate_artifacts.py") extract-verified --archive (Join-Path $fixture "reserved.zip") --authorization (Join-Path $fixture "authorization.json") --extract (Join-Path $fixture "reserved-output"); exit $LASTEXITCODE
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
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures-1c0901d"; & python (Join-Path $base "scripts\candidate\record.py") --archive (Join-Path $fixture "record.zip") --name authorization.json --out (Join-Path $fixture "record-output.json"); exit $LASTEXITCODE
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
$base="CHECKOUT"; $fixture="NATIVE-TEMP\fixtures-1c0901d"; & python (Join-Path $base "scripts\candidate\record.py") --archive (Join-Path $fixture "extra.zip") --name authorization.json --out (Join-Path $fixture "extra-output.json"); exit $LASTEXITCODE
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

## B06-invocation-error

Command:

```text
$ErrorActionPreference="Stop"; $root="NATIVE-TEMP\B06"; Set-Location $root; $env:SIGNING_LOG_CONFIG="NATIVE-TEMP\signing\log4j2-off.xml"; $env:ES_USERNAME="dummy-user-not-a-real-account"; $env:ES_PASSWORD="dummy-password-not-a-real-secret"; $env:ES_TOTP_SECRET="ZHVtbXktc2VlZC1ub3QtYS1yZWFsLXNlY3JldA=="; & "NATIVE-TEMP\jdk-ci\jdk-17.0.20+8\bin\java.exe" -Dfile.encoding=UTF-8 -XX:-HeapDumpOnOutOfMemoryError -XX:ErrorFile=NUL -cp "$root\classes;$root\code_sign_tool-1.3.3.jar" CodeSignRunner self-test; exit $LASTEXITCODE
```

Exit: 1.

```text
Error: Could not find or load main class .encoding=UTF-8
Caused by: java.lang.ClassNotFoundException: /encoding=UTF-8
```

## B06-Windows

Command:

```text
$ErrorActionPreference="Stop"; $root="NATIVE-TEMP\B06"; Set-Location $root; $env:SIGNING_LOG_CONFIG="NATIVE-TEMP\signing\log4j2-off.xml"; $env:ES_USERNAME="dummy-user-not-a-real-account"; $env:ES_PASSWORD="dummy-password-not-a-real-secret"; $env:ES_TOTP_SECRET="ZHVtbXktc2VlZC1ub3QtYS1yZWFsLXNlY3JldA=="; & "NATIVE-TEMP\jdk-ci\jdk-17.0.20+8\bin\java.exe" "-Dfile.encoding=UTF-8" "-XX:-HeapDumpOnOutOfMemoryError" "-XX:ErrorFile=NUL" -cp "$root\classes;$root\code_sign_tool-1.3.3.jar" CodeSignRunner self-test; exit $LASTEXITCODE
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
bbcc59f266b2de717c1fff6345f47e5275cf97ceb05ac3b7a5887096211a1f11  FIXTURE/case.zip
d260524b3fd60389236460174efb5eaf0df0a019229393fd2be1f213ba533dbf  FIXTURE/extra.zip
acf2ae992721cdfcea798184f4b829ad0315b50a4ba928b8071a48f1d7c2e4b7  FIXTURE/record.zip
18f4929a96592da1924dd09e7843955ce78ecc8c59311efd9b5ea06b64247b75  FIXTURE/reserved.zip
c52e29dba90f959ef5fc8eee10995717b123895e7c63db2438c4943db6e186c9  FIXTURE/symlink.zip
7608938e75ba65d56065ccb86bad0198136b446b7afdffa9d4bec36a71e4c49b  FIXTURE/traversal.zip
3a7ea1a18cd942bd4e0037ce73a3335ffb24745e01881385f86f75474baf0ee5  FIXTURE/authorization.json
3a7ea1a18cd942bd4e0037ce73a3335ffb24745e01881385f86f75474baf0ee5  FIXTURE/record-output.json
```

## oracle-Windows

Command:

```text
$ErrorActionPreference="Stop"; $fixture="NATIVE-TEMP\fixtures-1c0901d"; foreach($name in @("materialized","preflight.json","traversal-output","symlink-output","case-output","reserved-output","extra-output.json")){if(Test-Path (Join-Path $fixture $name)){throw "Unexpected output: $name"}}; if(Test-Path "NATIVE-TEMP\outside.txt"){throw "Escaped output"}; $hashes=Get-Content (Join-Path $fixture "fixture-hashes.json") -Raw | ConvertFrom-Json; foreach($property in $hashes.PSObject.Properties){if((Get-FileHash (Join-Path $fixture $property.Name)).Hash.ToLower() -ne $property.Value){throw "Fixture changed"}}; if((Get-FileHash (Join-Path $fixture "authorization.json")).Hash -ne (Get-FileHash (Join-Path $fixture "record-output.json")).Hash){throw "Record changed"}; foreach($name in @("B04-Windows","B05-Windows")){if(Test-Path "NATIVE-TEMP\fixtures\$name"){throw "Signer wrote output"}}; Write-Output "PASS: fixtures unchanged; no refused output; no escaped path; exact record copy; no signing ledger."
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
