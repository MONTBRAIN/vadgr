"""Protected shared helper coordination. No operation here invokes a signer."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import os
from pathlib import Path
import sys
import uuid
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import candidate_claims as claims
from scripts import candidate_artifacts as artifacts
from scripts import cua_profiles
from scripts.candidate import cua_helpers as helpers
from scripts.validate_package_inputs import PackageInputError, read_owned, require, sha256_bytes

CLAIM = "pre-signing-claim.json"
POLICY = "publisher-policy.json"
REPORTS = "signature-reports.json"
MANIFEST = "broker-final-manifest.json"
MAPPING = "input-output.json"


def read(path):
    return helpers.document(Path(path).read_bytes())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(value if isinstance(value, bytes) else helpers.canonical(value))


def package_file(root, relative):
    matches = [p for p in root.rglob(Path(relative).name)
               if p.is_file() and p.relative_to(root).as_posix().endswith("/" + relative)]
    require(len(matches) == 1, "profile package member is absent or ambiguous")
    path = matches[0].relative_to(root).as_posix()
    return path, read_owned(root, path)


def stage(auth, native_root, wsl_root, trusted, wsl_metadata, output):
    require(not output.exists(), "shared helper inputs already exist")
    architecture = {"x64": "x86_64", "arm64": "aarch64"}[auth["architecture"]]
    policy_raw = read_owned(trusted, f"packaging/cua/helper-signing/{architecture}.json")
    policy = helpers.document(policy_raw)
    require(sha256_bytes(policy_raw) in auth["legal_hashes"].values(),
            "exact helper trust policy is not in approved legal inputs")
    require(wsl_metadata["run_id"] == auth["run_id"] and wsl_metadata["run_attempt"] == 1
            and wsl_metadata["producer_sha"] == auth["trusted_sha"], "WSL producer identity differs")
    manifests, bindings, locations, common = {}, {}, {}, None
    for profile, root, candidate_hash in (
        ("windows-" + architecture, native_root, auth["unsigned_artifact_digest"].removeprefix("sha256:")),
        ("wsl-" + architecture, wsl_root, wsl_metadata["artifact_digest"].removeprefix("sha256:")),
    ):
        _, pins, catalog = cua_profiles.reviewed(trusted, trusted, profile)
        _, raw = package_file(root, f"computer_use/browser/profiles/{profile}/cua-profile-manifest.json")
        require(sha256_bytes(raw) == pins["profiles"][profile]["role_manifest_sha256"],
                "installed profile manifest differs from reviewed bytes")
        manifest = claims.parse(raw)
        data, located = {}, {}
        for key in ("relay", "archive", "member_manifest"):
            row = manifest["helpers"][key]
            located[key], data[key] = package_file(root, row["path"])
            require(sha256_bytes(data[key]) == row["sha256"] and len(data[key]) == row["size"],
                    "actual consumer helper input differs")
        require(common is None or common == data, "independently measured input closures differ")
        common, manifests[profile], locations[profile] = data, manifest, located
        bindings[profile] = {"candidate_sha256": candidate_hash, "catalog_sha256": pins["catalog_sha256"],
                             "lock_sha256": pins["profiles"][profile]["requirements_sha256"],
                             "wheel_sha256": pins["profiles"][profile]["wheel_sha256"]}
    relay_path = "relay.exe"
    files = helpers.archive_members(common["archive"])
    require(relay_path not in files, "relay staging name collides with broker member")
    files[relay_path] = common["relay"]
    request = {"architecture": architecture, "cua_version": catalog["cua_version"],
               "source_commit": catalog["source_commit"], "tooling_commit": auth["trusted_sha"],
               "consumer_inputs": bindings, "legal_policy_sha256": auth["legal_approval_sha256"],
               "signing_run_id": auth["run_id"], "signing_job_id": "sign-shared-helper"}
    claim = helpers.prepare(request, manifests, files, policy, relay_path,
                            input_archive=common["archive"], input_manifest=common["member_manifest"])
    predecessor = read_owned(trusted, f"packaging/cua/helper-signing/{architecture}-predecessors.json")
    for name, data in {CLAIM: helpers.canonical(claim), POLICY: policy_raw,
                       "input-broker.zip": common["archive"], "input-member-manifest.json": common["member_manifest"],
                       "input-index.json": helpers.canonical({"relay_path": relay_path,
                         "archive_path": manifests["windows-" + architecture]["helpers"]["archive"]["path"],
                         "predecessor_catalog_sha256": sha256_bytes(predecessor), "locations": locations})}.items():
        write(output / name, data)
    for name, data in files.items():
        write(output / "members" / name, data)
    return claim


def bind(auth, inputs, artifact_id, artifact_digest, wsl_metadata, trusted):
    raw = read_owned(inputs, CLAIM)
    helper = helpers.document(raw)
    outer_raw = read_owned(trusted, f"packaging/cua/helper-signing/{helper['architecture']}-outer.json")
    policy = helpers.document(outer_raw)
    require(sha256_bytes(outer_raw) in auth["legal_hashes"].values(),
            "outer trust policy is not in approved legal inputs")
    require(policy["schema"] == 1 and set(policy) == {"schema", "files"}, "outer policy schema differs")
    outer = policy["files"]
    require(all(path in auth["files"] and row["input_sha256"] == auth["files"][path]["sha256"]
                for path, row in outer.items()), "outer policy does not bind approved files")
    operations = sum(row["trust_class"] == "publisher-sign" for row in outer.values()) + 3
    return {**auth, "helper_claim_sha256": sha256_bytes(raw),
            "helper_policy_sha256": sha256_bytes(read_owned(inputs, POLICY)),
            "helper_input_artifact_id": artifact_id, "helper_input_artifact_digest": artifact_digest,
            "wsl_artifact_id": wsl_metadata["artifact_id"], "wsl_artifact_digest": wsl_metadata["artifact_digest"],
            "helper_signing_operations": helper["signing_operations"], "outer_signing_operations": operations,
            "signing_policy": policy, "budget": operations + helper["signing_operations"]}


def ledger_init(path, auth):
    write(path, {"schema": 2, "authorization_sha256": claims.digest(claims.canonical(auth)),
                 "budget": auth["budget"], "attempts": []})


def ledger_update(path, auth, unit, relative, input_hash, claim_hash, output_hash=None):
    require(unit in ("shared-helper", "outer", "vehicle"), "unknown signing unit")
    helpers.relative_path(relative)
    helpers.digest(input_hash)
    helpers.digest(claim_hash)
    lock = path.with_name(path.name + ".lock")
    # Exclusive creation rejects simultaneous attempts instead of retrying vendor use.
    lock_stream = lock.open("xb")
    try:
        try:
            ledger = read(path)
            require(ledger["schema"] == 2 and ledger["budget"] == auth["budget"]
                    and ledger["authorization_sha256"] == claims.digest(claims.canonical(auth)),
                    "signer ledger authorization differs")
            matching = [r for r in ledger["attempts"] if r["unit"] == unit and r["path"] == relative]
            if output_hash is None:
                require(not matching and len(ledger["attempts"]) < ledger["budget"],
                        "duplicate signing operation or quota overrun")
                ledger["attempts"].append({"unit": unit, "path": relative, "input_sha256": input_hash,
                    "claim_sha256": claim_hash, "status": "reserved", "output_sha256": None})
            else:
                helpers.digest(output_hash)
                require(len(matching) == 1 and matching[0]["status"] == "reserved"
                        and matching[0]["input_sha256"] == input_hash
                        and matching[0]["claim_sha256"] == claim_hash, "signer completion has no exact reservation")
                matching[0].update(status="verified", output_sha256=output_hash)
            temporary = path.with_name(path.name + "." + uuid.uuid4().hex)
            write(temporary, ledger)
            temporary.replace(path)
        finally:
            lock_stream.close()
    finally:
        lock.unlink()


def ledger_complete(path, auth):
    ledger = read(path)
    require(set(ledger) == {"schema", "authorization_sha256", "budget", "attempts"}
            and ledger["schema"] == 2
            and ledger["authorization_sha256"] == claims.digest(claims.canonical(auth))
            and ledger["budget"] == auth["budget"] and len(ledger["attempts"]) == auth["budget"]
            and all(row["status"] == "verified" for row in ledger["attempts"]),
            "signer ledger contains missing or uncertain operations")
    expected_outer = {path for path, row in auth["signing_policy"]["files"].items()
                      if row["trust_class"] == "publisher-sign"}
    expected_vehicles = {f"Vadgr-0.5.0-windows-{auth['architecture']}.msi", "burn-engine.exe",
                         f"Vadgr-0.5.0-windows-{auth['architecture']}-final.exe"}
    observed = {unit: [] for unit in ("shared-helper", "outer", "vehicle")}
    for row in ledger["attempts"]:
        require(set(row) == {"unit", "path", "input_sha256", "claim_sha256", "status", "output_sha256"}
                and row["unit"] in observed, "signing ledger row schema differs")
        helpers.relative_path(row["path"])
        helpers.digest(row["input_sha256"])
        helpers.digest(row["output_sha256"])
        if row["unit"] == "shared-helper":
            require(row["claim_sha256"] == auth["helper_claim_sha256"], "helper ledger claim differs")
        if row["unit"] == "outer":
            require(row["path"] in expected_outer and row["input_sha256"] == auth["files"][row["path"]]["sha256"],
                    "outer ledger does not bind approved publisher input")
        observed[row["unit"]].append(row["path"])
    require(all(len(paths) == len(set(paths)) for paths in observed.values())
            and len(observed["shared-helper"]) == auth["helper_signing_operations"]
            and set(observed["outer"]) == expected_outer
            and set(observed["vehicle"]) == expected_vehicles,
            "signing ledger does not contain the exact shared/outer/vehicle operations")
    return ledger


def observe(root, inputs, output, profile):
    claim = read(inputs / CLAIM)
    require(profile in helpers.pair(claim["architecture"]), "unexpected helper consumer")
    locations = read(inputs / "input-index.json")["locations"][profile]
    expected = read(output / MANIFEST)
    # The profile finalizer writes to its own copied runtime, then measures it.
    for key, name in (("relay", "relay.exe"), ("archive", "broker.zip")):
        destination = root / locations[key]
        read_owned(root, locations[key])  # Validate all parent components before writing.
        require(not destination.is_symlink(), "linked consumer helper destination")
        with destination.open("wb") as stream:
            stream.write(read_owned(output, name))
    final_manifest = Path(locations["archive"]).parent / MANIFEST
    write(root / final_manifest, read_owned(output, MANIFEST))
    observed = measured(root, {"relay_sha256": locations["relay"], "archive_sha256": locations["archive"],
                               "manifest_sha256": final_manifest.as_posix()})
    require(observed["archive_sha256"] == expected["archive"]["sha256"], "consumer archive copy differs")
    return {"schema": 1, "profile": profile,
            "input_candidate_sha256": claim["consumer_inputs"][profile]["candidate_sha256"],
            "final_closure": observed}


def shared_policy(api):
    policies, protected = [], set()
    for summary in claims.pages(api, "rulesets?includes_parents=true&targets=tag"):
        rule = claims.get(api, f"rulesets/{summary['id']}")
        if rule.get("enforcement") != "active" or rule.get("target") != "tag":
            continue
        refs = rule.get("conditions", {}).get("ref_name", {})
        if not any(p in {"~ALL", "refs/tags/cua-signing-claims/**"} for p in refs.get("include", [])):
            continue
        require(not refs.get("exclude"), "shared helper claim protection has exclusions")
        kinds = {row.get("type") for row in rule.get("rules", [])} & {"update", "deletion"}
        if kinds:
            require(rule.get("bypass_actors") == [], "shared claim rules allow mutation bypass")
            protected.update(kinds)
        policies.append(rule)
    require(protected == {"update", "deletion"}, "shared claim update/deletion protections absent")
    return sha256_bytes(helpers.canonical(sorted(policies, key=lambda row: row["id"])))


def probe_shared(api, auth):
    """Qualify the actual shared namespace before any credential-bearing job."""
    policy = shared_policy(api)
    ref = f"refs/tags/cua-signing-claims/probe/{auth['run_id']}-1"
    require(api.request("GET", claims.PREFIX + "git/ref/" + ref[5:])[0] == 404,
            "shared claim probe already exists; no retry")
    parent = claims.get(api, "git/commits/" + auth["trusted_sha"])["parents"][0]["sha"]
    require(claims.hashed(parent, 40) and parent != auth["trusted_sha"], "distinct probe target absent")
    tag = claims.tag_create(api, ref, auth["trusted_sha"], {"shared_helper_probe": claims.identity(auth)})
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(api.request, "POST", claims.PREFIX + "git/refs", {"ref": ref, "sha": tag})
                   for _ in range(2)]
        results = [future.result() for future in futures]
    require(sorted(code for code, _ in results) == [201, 422]
            and "already exists" in next(body for code, body in results if code == 422).get("message", "").lower(),
            "shared claim competing-create proof failed")
    claims.check_ref(api, ref, tag)
    for method, body in (("PATCH", {"sha": parent, "force": True}), ("DELETE", None)):
        code, result = api.request(method, claims.PREFIX + "git/refs/" + ref[5:], body)
        require(code in {403, 422} and "rule" in result.get("message", "").lower(),
                "shared claim mutation not denied by a protected rule")
        claims.check_ref(api, ref, tag)
    require(shared_policy(api) == policy, "shared claim policy changed during probe")
    return {"schema": 1, "policy_sha256": policy, "ref": ref, "tag": tag,
            "results": {"create": 201, "duplicate": 422, "update_denied": True, "delete_denied": True}}


def check_bound_helper(auth, raw):
    claim = helpers.document(raw)
    require(auth["helper_claim_sha256"] == sha256_bytes(raw)
            and auth["helper_policy_sha256"] == claim["publisher_policy_sha256"]
            and auth["helper_signing_operations"] == claim["signing_operations"]
            and auth["budget"] == auth["outer_signing_operations"] + claim["signing_operations"]
            and claim["signing_run_id"] == auth["run_id"] and claim["signing_attempt"] == 1
            and claim["tooling_commit"] == auth["trusted_sha"]
            and claim["architecture"] == {"x64": "x86_64", "arm64": "aarch64"}[auth["architecture"]],
            "protected shared helper tuple differs")
    expected = sha256_bytes(helpers.canonical({"architecture": claim["architecture"],
                                             "input_closure": claim["input_closure"]}))
    require(claim["helper_closure_id"] == expected
            and claim["signing_claim_ref"] == "refs/tags/cua-signing-claims/" + expected,
            "shared claim key is not the architecture/input closure")
    return claim


def create_shared(api, auth, qualification, raw):
    claims.validate_live(api, auth, qualification)
    claim = check_bound_helper(auth, raw)
    probe = probe_shared(api, auth)
    ref = claim["signing_claim_ref"]
    require(api.request("GET", claims.PREFIX + "git/ref/" + ref[5:])[0] == 404,
            "shared helper closure already spent")
    message = {"schema": 1, "authorization_sha256": claims.digest(claims.canonical(auth)),
               "pre_signing_claim_sha256": sha256_bytes(raw), "probe": probe}
    tag = claims.tag_create(api, ref, auth["source_sha"], message)
    code, _ = api.request("POST", claims.PREFIX + "git/refs", {"ref": ref, "sha": tag})
    require(code == 201, "shared helper claim raced or uncertain; no retry")
    receipt = {"schema": 1, "ref": ref, "tag": tag, **message}
    verify_shared(api, auth, qualification, raw, receipt)
    return receipt


def verify_shared(api, auth, qualification, raw, receipt):
    claims.validate_live(api, auth, qualification)
    claim = check_bound_helper(auth, raw)
    require(set(receipt) == {"schema", "ref", "tag", "authorization_sha256", "pre_signing_claim_sha256", "probe"}
            and receipt["schema"] == 1 and receipt["ref"] == claim["signing_claim_ref"]
            and receipt["authorization_sha256"] == claims.digest(claims.canonical(auth))
            and receipt["pre_signing_claim_sha256"] == sha256_bytes(raw), "shared durable claim differs")
    probe = receipt["probe"]
    require(probe["policy_sha256"] == shared_policy(api)
            and probe["ref"] == f"refs/tags/cua-signing-claims/probe/{auth['run_id']}-1"
            and probe["results"] == {"create": 201, "duplicate": 422, "update_denied": True, "delete_denied": True},
            "shared namespace proof differs")
    claims.check_ref(api, probe["ref"], probe["tag"])
    claims.check_ref(api, receipt["ref"], receipt["tag"])
    tag = claims.get(api, "git/tags/" + receipt["tag"])
    require(tag["object"]["sha"] == auth["source_sha"] and tag["object"]["type"] == "commit"
            and claims.parse(tag["message"]) == {k: receipt[k] for k in (
                "schema", "authorization_sha256", "pre_signing_claim_sha256", "probe")},
            "shared durable claim object differs")


def measured(root, paths):
    """Read each consumer's actual copied bytes. Never copy expected hashes."""
    return {key: sha256_bytes(read_owned(root, path)) for key, path in paths.items()}


def fetch(artifact_id, artifact_digest, output, architecture):
    """Fetch only the exact same-run immutable artifact, then safely expand it."""
    require(not output.exists(), "artifact extraction destination already exists")
    archive, metadata = output.with_suffix(".zip"), output.with_suffix(".metadata.json")
    artifacts.download(SimpleNamespace(artifact_id=artifact_id, digest=artifact_digest,
        run_id=int(os.environ["GITHUB_RUN_ID"]), run_attempt=1, repository=claims.REPOSITORY,
        producer_sha=os.environ["GITHUB_SHA"], architecture=architecture, out=archive, metadata=metadata))
    # ZIP names/duplicates/special members/sizes are checked before any extraction.
    members, total = {}, 0
    with zipfile.ZipFile(archive) as source:
        seen = set()
        for item in source.infolist():
            require(artifacts.safe_name(item.filename) and item.filename.casefold() not in seen,
                    "unsafe or duplicate artifact path")
            seen.add(item.filename.casefold())
            mode = item.external_attr >> 16
            require((mode & 0o170000) in (0, 0o100000, 0o040000), "special artifact member")
            if item.is_dir():
                continue
            total += item.file_size
            require(total <= artifacts.MAX_EXPANDED and len(seen) <= artifacts.MAX_FILES, "artifact limits exceeded")
            raw = source.read(item)
            require(len(raw) == item.file_size, "artifact member length differs")
            members[item.filename] = raw
    for name, raw in members.items():
        write(output / name, raw)
    return claims.parse(metadata.read_bytes())


def summarize_ledger(claim_raw, ledger):
    claim = helpers.document(claim_raw)
    require(set(ledger) == {"schema", "authorization_sha256", "budget", "attempts"}
            and ledger["schema"] == 2 and type(ledger["budget"]) is int, "real signer ledger required")
    attempts = [row for row in ledger["attempts"] if row["unit"] == "shared-helper"]
    expected = set(claim["publisher_sign_paths"])
    require(len(attempts) == len(expected) and {row["path"] for row in attempts} == expected
            and all(row["status"] == "verified" and row["claim_sha256"] == sha256_bytes(claim_raw)
                    and helpers.digest(row["input_sha256"]) and helpers.digest(row["output_sha256"])
                    for row in attempts), "actual helper ledger is incomplete, repeated or uncertain")
    return [{"pre_signing_claim_sha256": sha256_bytes(claim_raw),
             "helper_closure_id": claim["helper_closure_id"], "operations": len(attempts)}]


def finalize_directory(inputs, signed, output):
    require(not output.exists(), "helper output already frozen")
    raw = read_owned(inputs, CLAIM)
    claim, policy, index = helpers.document(raw), read(inputs / POLICY), read(inputs / "input-index.json")
    before = {name: read_owned(inputs / "members", name) for name in policy["files"]}
    after = {name: read_owned(signed, name) for name in policy["files"]}
    reports = {name: helpers.canonical(value) for name, value in read(signed / REPORTS).items()}
    archive, manifest, mapping = helpers.finalize(raw, before, after, policy, reports,
        relay_path=index["relay_path"], archive_path=index["archive_path"],
        predecessor_catalog_sha256=index["predecessor_catalog_sha256"],
        input_archive=read_owned(inputs, "input-broker.zip"),
        input_manifest=read_owned(inputs, "input-member-manifest.json"))
    for name, data in {CLAIM: raw, POLICY: helpers.canonical(policy), MANIFEST: manifest, MAPPING: mapping,
                       REPORTS: helpers.canonical({p: helpers.document(r) for p, r in reports.items()}),
                       "relay.exe": after[index["relay_path"]], "broker.zip": archive}.items():
        write(output / name, data)
    return claim


def authorize_directory(output, artifact, ledger, native_observation, wsl_observation, destination):
    require(not destination.exists(), "helper authorization output already exists")
    raw = read_owned(output, CLAIM)
    claim = helpers.document(raw)
    mapping = read(output / MAPPING)
    mapped = {row["path"]: row for row in mapping["files"]}
    for row in ledger["attempts"]:
        require(row["unit"] == "shared-helper" and row["path"] in mapped
                and row["input_sha256"] == mapped[row["path"]]["input_sha256"]
                and row["output_sha256"] == mapped[row["path"]]["sha256"],
                "real helper ledger does not bind actual transformed bytes")
    observations = {}
    for value, profile in zip((native_observation, wsl_observation), helpers.pair(claim["architecture"])):
        require(set(value) == {"schema", "profile", "input_candidate_sha256", "final_closure"}
                and value["schema"] == 1 and value["profile"] == profile
                and value["input_candidate_sha256"] == claim["consumer_inputs"][profile]["candidate_sha256"],
                "independent consumer observation identity differs")
        observations[profile] = value["final_closure"]
    auth, receipts = helpers.authorize(raw, read_owned(output, MANIFEST), read_owned(output, MAPPING),
        read_owned(output, "relay.exe"), artifact, summarize_ledger(raw, ledger), observed_consumers=observations)
    write(destination / "helper-closure-authorization.json", auth)
    for profile, receipt in receipts.items():
        write(destination / ("receipt-wsl.json" if profile.startswith("wsl-") else "receipt-windows.json"), receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    command = sub.add_parser("fetch")
    command.add_argument("--artifact-id", type=int, required=True)
    command.add_argument("--digest", required=True)
    command.add_argument("--out", type=Path, required=True)
    command.add_argument("--architecture", choices=("x64", "arm64"), required=True)
    for mode in ("canonical-reports", "canonical-receipt"):
        command = sub.add_parser(mode)
        command.add_argument("--input", type=Path, required=True)
        command.add_argument("--out", type=Path, required=True)
    command = sub.add_parser("stage")
    for name in ("authorization", "native-root", "wsl-root", "trusted-root", "wsl-metadata", "out"):
        command.add_argument("--" + name, type=Path, required=True)
    command = sub.add_parser("bind")
    for name in ("authorization", "inputs", "wsl-metadata", "trusted-root", "out"):
        command.add_argument("--" + name, type=Path, required=True)
    command.add_argument("--artifact-id", type=int, required=True)
    command.add_argument("--artifact-digest", required=True)
    command = sub.add_parser("observe")
    for name in ("root", "inputs", "output", "out"):
        command.add_argument("--" + name, type=Path, required=True)
    command.add_argument("--profile", required=True)
    for mode in ("ledger-init", "ledger-reserve", "ledger-verify", "ledger-complete"):
        command = sub.add_parser(mode)
        command.add_argument("--ledger", type=Path, required=True)
        command.add_argument("--authorization", type=Path, required=True)
        if mode in ("ledger-reserve", "ledger-verify"):
            for name in ("unit", "path", "input-sha256", "claim-sha256"):
                command.add_argument("--" + name, required=True)
        if mode == "ledger-verify":
            command.add_argument("--output-sha256", required=True)
    for mode in ("claim", "verify-claim"):
        command = sub.add_parser(mode)
        command.add_argument("--authorization", type=Path, required=True)
        command.add_argument("--qualification", type=Path, required=True)
        command.add_argument("--helper-inputs", type=Path, required=True)
        command.add_argument("--shared-claim", type=Path, required=True)
    command = sub.add_parser("finalize")
    command.add_argument("--inputs", type=Path, required=True)
    command.add_argument("--signed", type=Path, required=True)
    command.add_argument("--out", type=Path, required=True)
    command = sub.add_parser("authorize")
    for name in ("output", "artifact", "ledger", "native-observation", "wsl-observation", "out"):
        command.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.mode == "fetch":
            fetch(args.artifact_id, args.digest, args.out.absolute(), args.architecture)
        elif args.mode in ("canonical-reports", "canonical-receipt"):
            value = claims.parse(args.input.read_text(encoding="utf-8-sig"))
            require(isinstance(value, dict) and bool(value), "empty signature evidence")
            if args.mode == "canonical-receipt":
                for row in value.values():
                    report = row.pop("signature_report")
                    require(set(report) == helpers.REPORT_KEYS, "signature report fields differ")
                    row["signature_report_sha256"] = sha256_bytes(helpers.canonical(report))
            else:
                require(all(set(row) == helpers.REPORT_KEYS for row in value.values()), "signature report fields differ")
            write(args.out, value)
        elif args.mode == "stage":
            stage(claims.parse(args.authorization.read_bytes()), args.native_root.resolve(),
                  args.wsl_root.resolve(), args.trusted_root.resolve(),
                  claims.parse(args.wsl_metadata.read_bytes()), args.out.absolute())
        elif args.mode == "bind":
            write(args.out, bind(claims.parse(args.authorization.read_bytes()), args.inputs.resolve(),
                  args.artifact_id, args.artifact_digest, claims.parse(args.wsl_metadata.read_bytes()),
                  args.trusted_root.resolve()))
        elif args.mode == "observe":
            write(args.out, observe(args.root.resolve(), args.inputs.resolve(), args.output.resolve(), args.profile))
        elif args.mode.startswith("ledger-"):
            auth = claims.parse(args.authorization.read_bytes())
            if args.mode == "ledger-init":
                ledger_init(args.ledger, auth)
            elif args.mode == "ledger-complete":
                ledger_complete(args.ledger, auth)
            else:
                ledger_update(args.ledger, auth, args.unit, args.path, args.input_sha256,
                              args.claim_sha256, getattr(args, "output_sha256", None))
        elif args.mode in ("claim", "verify-claim"):
            auth = claims.parse(args.authorization.read_bytes())
            require(os.environ.get("GITHUB_REPOSITORY") == claims.REPOSITORY
                    and os.environ.get("GITHUB_REF") == "refs/heads/master"
                    and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
                    and os.environ.get("GITHUB_RUN_ID") == str(auth["run_id"])
                    and os.environ.get("GITHUB_SHA") == auth["trusted_sha"], "fixed workflow context required")
            raw = read_owned(args.helper_inputs.resolve(), CLAIM)
            qualification = claims.parse(args.qualification.read_bytes())
            if args.mode == "claim":
                write(args.shared_claim, create_shared(claims.GitHubAPI(), auth, qualification, raw))
            else:
                verify_shared(claims.GitHubAPI(), auth, qualification, raw, read(args.shared_claim))
        elif args.mode == "finalize":
            finalize_directory(args.inputs.resolve(), args.signed.resolve(), args.out.absolute())
        else:
            authorize_directory(args.output.resolve(), read(args.artifact), read(args.ledger),
                                read(args.native_observation), read(args.wsl_observation), args.out.absolute())
    except (PackageInputError, claims.Refused, OSError, KeyError, ValueError, TypeError):
        print("Shared helper operation refused; no signing request was made.", file=sys.stderr)
        return 2
    print("Shared helper operation verified; no signing request was made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
