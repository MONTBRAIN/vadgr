# Windows signing service qualification

Status: S1 partial. Native Windows inspection succeeded in run `35161663373`
at `c160b5f94f891e450477658f29fa8b8344e7604d`, but independent public certificate
comparison remains pending. S2 is blocked; zero signatures were requested.
The first attempt failed during Java setup, before service authentication.
Neither live cell has fully passed. This is an isolated two-cell service test, not a product release
or installer acceptance pass. The branch is `signing-smoke-iv-20260916`, based
on `e4e9ff2`. Record the exact committed test head and Actions run URL before
each cell. No release, tag, installer, or signed artifact is published.

The initial workflow can inspect certificates only. It has no TOTP input and
cannot select the signing mode. A separate reviewed change is required to
enable the second cell. The existing release workflow is unchanged.

## Prerequisites

| Requirement | Cells | Non-secret check | Cost and cleanup |
|---|---|---|---|
| SSL.com account with issued code-signing certificate | S1, S2 | Protected environment contains `ES_USERNAME` and `ES_PASSWORD`; read secret names only | Authentication is account-wide. Never store credentials in files, arguments, or logs |
| GitHub `release-windows` environment | S1, S2 | Required owner reviewer, no bypass, only exact temporary branch added beside existing tag policy | Owner approves the immutable job head. Remove the temporary branch allowance after the test |
| Current pinned Java and CodeSignTool | S1, S2 | ZIP and JAR SHA-256 checks; compile with annotation processing disabled | Standard ephemeral Windows runner; no cache or artifact upload |
| Publisher certificate bundle independently obtained from SSL.com | S1, S2 | Owner compares public subject, issuer, validity and certificate SHA-256 with the inspection result | Public certificate only; no private key exists on the runner |
| eSigner subscription and TOTP enrollment | S2 | `ES_TOTP_SECRET` exists; runtime accepts vendor Base64 representation without printing it | At most one signing request; no automatic or manual rerun of a failed job |
| Approved subject and SHA-256 fingerprint | S2 | Reviewed `EXPECTED_CERT_SUBJECT` and `EXPECTED_CERT_SHA256`; explicit `APPROVED_SIGNATURE_COUNT=1` | Never infer either from the output being signed |
| Windows SDK SignTool and Windows certificate trust | S2 | Locate verifier before any signature request | Timestamp and chain verification use network access |

No certificate, device, firewall, DNS, proxy, or account setting changes form
part of this test. The owner supplies only protected environment approval and
independent confirmation of public certificate identity.

## Automated gate

Run `python3 -m pytest scripts/tests -q` and the repository credential scan.
Run `scripts/signing/test-launcher.ps1 -VendorRoot <verified-package-directory>`
on native Windows with dummy credentials only. The test compiles the real
launcher, writes dummy values to the suppressed output streams and Log4j,
checks the vendor missing-file refusal, scans raw output and generated files,
and confirms that no vendor log directory exists. This proves the tested
failure path, not remote service acceptance or every possible vendor error.
The X.500 check also proves that comma-spacing differences do not change the
pre-sign subject comparison.

## Live cells

| ID | Precondition | Setup and action | Expected observable | Independent oracle | Evidence boundary | Cleanup | Result |
|---|---|---|---|---|---|---|---|
| S1 | Automated gate passed; owner reviewed exact inspect-only head; required reviewer and exact branch policy confirmed; account secrets present | Push reviewed exact branch, then owner approves only the inspect job. Prepare pinned tool; authenticate; list the same EVCS/OVCS credential classes used by the vendor command; read public certificates | Only public subject, issuer, validity, SHA-256 and SHA-1 are printed. No credential ID, token, seed, password or signing response is printed. No signature is requested | Owner compares the public certificate bundle from SSL.com with the certificate SHA-256 and subject; verify the workflow has no TOTP environment input or sign-mode invocation | Record exact head, run URL, job conclusion, public certificate facts and owner comparison result in `evidence/signing-smoke/`; retain no authentication response or vendor log | Runner is ephemeral; do not approve signing if identity differs or no certificate appears | partial: run 35161663373 passed service inspection on native Windows and requested zero signatures; owner comparison with an independently obtained public certificate remains pending after portal session expiry |
| S2 | S1 passed; owner independently confirmed fingerprint and subject; separate reviewed sign-enabling change; one-sign quota approved; TOTP secret available | Owner approves distinct protected job. Build one inert EXE locally, verify unsigned state, preflight exact certificate, validity and code-signing EKU; reject online OTP; invoke one vendor sign operation with malware blocking; never execute sample | Exactly one signed inert sample. All signing failures stop with a fixed non-secret diagnostic. No retry, release or artifact upload | Windows SignTool `verify /pa /all /tw` returns zero; `Get-AuthenticodeSignature` returns Valid with timestamp certificate; signed leaf SHA-256 equals independently pinned certificate. Java verifies the X.500 subject before signing | Record exact head, run URL, exit codes, public publisher and timestamp facts, and sample SHA-256 in `evidence/signing-smoke/`; no tool raw debug logs or signed binary uploaded | Ephemeral runner discards files; remove temporary environment branch allowance after the test, including failure | blocked: S1 and separate sign-enabling review/approval are required; current workflow cannot sign |

## Research and limits

Checked 2026-09-16 against the
[vendor command guide](https://www.ssl.com/guide/esigner-codesigntool-command-guide/)
and the downloaded CodeSignTool 1.3.3 bytecode. The guide advertises automated
TOTP use but describes EV certificates. IV acceptance remains unproven until
the exact certificate passes S2. An empty credential list is a failed probe,
not proof that IV can never work.

The ZIP SHA-256 is
`317d429be3aa12a5f2c1ffdd575eab0cb0ce5e2408ab0056bcdcaab29875f73d`;
the JAR SHA-256 is
`caa356347aa64ba04666545d548dad87211c9aa960f16db8797a880a67ba91d1`.
The download URL is mutable, so any byte change blocks execution for review.
The bundled old runtime is not used by the hosted job.
The hosted job pins Temurin `17.0.20+8`; the Java setup action rejected the
four-component release version in the first attempt before authentication.

The vendor JAR logs to a rolling file by default. The launcher installs a
log-disabled configuration before vendor classes initialize and discards
vendor output. Only explicit public certificate fields and fixed status text
can reach the job log. The inspected API places credential classes in
`clientData`; this test does not invent an undocumented IV credential class.
It does not bypass the vendor's malware check or replace its signing protocol.

No local workstation receives live production credentials. Local testing uses
dummy values only. Windows verification of a cloud-signed inert sample proves
the service and certificate path, not installer trust or Smart App Control
reputation. Those remain separate acceptance tests.
