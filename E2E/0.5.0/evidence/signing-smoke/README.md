# Signing probe record

No live service call or signature has run. This directory existed before S1.

## Attempt 1: setup failure

Actions run [35160875240](https://github.com/MONTBRAIN/vadgr/actions/runs/35160875240)
tested commit `ba2474f`. The Java setup action rejected `17.0.20.1+1` as invalid
SemVer syntax. The job failed before the credential-bearing inspection step.
S1 did not pass. No SSL.com authentication or signing was attempted.

The correction pins the published Temurin `17.0.20+8` release, which uses the
supported three-component form. Its run is a separate attempt and has no
result yet.

Record the exact tested commit, Actions run URL, job conclusion and public
certificate verification facts at each cell boundary. Add only sanitized
public results. Do not add credentials, credential identifiers, authentication
responses, vendor debug logs, process environments or signed binaries.

The local dummy checks do not establish service acceptance or a valid signature.
