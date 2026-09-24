"""Profile-aware signed helper insertion and runtime authorization reseal."""

from __future__ import annotations

from pathlib import Path
import json
import subprocess

if __package__ == "scripts.candidate":
    from scripts.candidate import cua_helpers as helpers, cua_signing as signing
    from scripts import cua_release_inputs as release
    from scripts.validate_package_inputs import canonical_json, parse_json, read_owned, require, sha256_bytes
else:
    from candidate import cua_helpers as helpers, cua_signing as signing
    import cua_release_inputs as release
    from validate_package_inputs import canonical_json, parse_json, read_owned, require, sha256_bytes


def verify_subject(subject, bundle, auth):
    trusted = Path(__file__).resolve().parents[2]
    require(sha256_bytes(read_owned(trusted, release.TRUSTED_ROOT)) == release.TRUSTED_ROOT_SHA256,
            "helper attestation verifier root differs")
    result = subprocess.run([
        "gh", "attestation", "verify", str(subject),
        "--bundle", str(bundle), "--repo", "MONTBRAIN/vadgr",
        "--cert-identity", "https://github.com/MONTBRAIN/vadgr/.github/workflows/candidate.yml@refs/heads/master",
        "--cert-oidc-issuer", "https://token.actions.githubusercontent.com", "--source-ref", "refs/heads/master",
        "--source-digest", auth["trusted_sha"], "--signer-digest", auth["trusted_sha"],
        "--custom-trusted-root", str(trusted / release.TRUSTED_ROOT), "--deny-self-hosted-runners",
        "--format", "json",
    ], capture_output=True, timeout=120, check=False)
    require(result.returncode == 0 and result.stdout, "shared helper attestation refused")
    def unique(items):
        value = {}
        for key, item in items:
            require(key not in value, "duplicate verified attestation key")
            value[key] = item
        return value
    verified = json.loads(result.stdout, object_pairs_hook=unique)
    require(isinstance(verified, list) and len(verified) == 1, "ambiguous verified attestation")
    certificate = verified[0]["verificationResult"]["signature"]["certificate"]
    subjects = verified[0]["verificationResult"]["statement"]["subject"]
    require(len(subjects) == 1 and subjects[0]["digest"] == {"sha256": sha256_bytes(subject.read_bytes())}
            and certificate["runInvocationURI"] == f"https://github.com/MONTBRAIN/vadgr/actions/runs/{auth['run_id']}/attempts/1"
            and certificate["sourceRepositoryDigest"] == auth["trusted_sha"]
            and certificate["buildSignerDigest"] == auth["trusted_sha"]
            and certificate["runnerEnvironment"] == "github-hosted",
            "attestation does not bind this exact protected run")


def verify_attestation(directory, auth):
    verify_subject(directory / "helper-closure-authorization.json", directory / "authorization.sigstore.json", auth)


def verify_runtime(root, auth):
    verify_subject(root / "cua-runtime-authorization.json", root / "cua-runtime-authorization.sigstore.json", auth)


def verify_outer_reports(receipt, reports, policy):
    require(isinstance(reports, dict) and set(reports) == set(receipt) == set(policy),
            "outer signature report set differs")
    for path, row in receipt.items():
        report, selected = reports[path], policy[path]
        require(set(report) == helpers.REPORT_KEYS and type(report["schema"]) is int and report["schema"] == 1
                and report["file_sha256"] == row["output"]["sha256"]
                and type(report["signtool_exit"]) is int and report["signtool_exit"] == 0
                and report["authenticode_status"] == "Valid" and report["chain_valid"] is True
                and report["timestamp_valid"] is True
                and all(report[key] == selected[key] for key in helpers.POLICY_KEYS - {"input_sha256"})
                and sha256_bytes(helpers.canonical(report)) == row["signature_report_sha256"],
                "outer signature report does not satisfy approved policy")


def helper_outputs(cua_root, payload, auth, directory):
    require(set(signing.tree(directory)) == signing.HELPER_RECORDS, "shared helper output file set differs")
    raw = {name: read_owned(directory, name) for name in signing.HELPER_RECORDS}
    verify_attestation(directory, auth)
    claim = helpers.document(raw["pre-signing-claim.json"])
    final = helpers.document(raw["broker-final-manifest.json"])
    authorization = helpers.document(raw["helper-closure-authorization.json"])
    policy = helpers.document(raw["publisher-policy.json"])
    reports = helpers.document(raw["signature-reports.json"])
    mapping = helpers.document(raw["input-output.json"])
    profile, architecture = payload["release_profile"], claim["architecture"]
    require(profile in helpers.pair(architecture) and payload["cua_version"] == claim["cua_version"]
            and sha256_bytes(raw["pre-signing-claim.json"]) == auth["helper_claim_sha256"]
            and sha256_bytes(raw["publisher-policy.json"]) == auth["helper_policy_sha256"]
            and claim["publisher_policy_sha256"] == auth["helper_policy_sha256"]
            and claim["signing_operations"] == auth["helper_signing_operations"]
            and claim["signing_run_id"] == auth["run_id"] and claim["signing_attempt"] == 1
            and claim["tooling_commit"] == auth["trusted_sha"]
            and claim["consumer_inputs"][profile]["lock_sha256"] == payload["requirements_sha256"],
            "shared helper claim differs from approved candidate")
    require(claim["consumer_inputs"]["windows-" + architecture]["candidate_sha256"] == auth["unsigned_artifact_digest"].removeprefix("sha256:")
            and claim["consumer_inputs"]["wsl-" + architecture]["candidate_sha256"] == auth["wsl_artifact_digest"].removeprefix("sha256:"),
            "shared helper claim does not bind both immutable consumer candidates")
    manifest_paths = [p for p in cua_root.rglob("cua-profile-manifest.json")
                      if p.parent.name == profile and p.parent.parent.name == "profiles"]
    require(len(manifest_paths) == 1, "installed input profile manifest is ambiguous")
    manifest_path = manifest_paths[0].relative_to(cua_root).as_posix()
    input_role_raw = read_owned(cua_root, manifest_path)
    require(sha256_bytes(input_role_raw) == payload["cua_profile_manifest_sha256"], "installed input role manifest changed")
    role = parse_json(input_role_raw)
    require(role["release_profile"] == profile and role["source_commit"] == claim["source_commit"],
            "installed role manifest source differs")
    # Fixed package prefix, derived from the exact pinned manifest location.
    suffix = f"computer_use/browser/profiles/{profile}/cua-profile-manifest.json"
    require(manifest_path.endswith(suffix), "installed profile manifest layout differs")
    package = manifest_path[:-len(suffix)]
    helper = role["helpers"]
    relay_path, archive_path = package + helper["relay"]["path"], package + helper["archive"]["path"]
    before_relay = read_owned(cua_root, relay_path)
    before_archive = read_owned(cua_root, archive_path)
    before_manifest = read_owned(cua_root, package + helper["member_manifest"]["path"])
    require(helpers.closure(role) == claim["input_closure"] and sha256_bytes(before_relay) == helper["relay"]["sha256"]
            and sha256_bytes(before_archive) == helper["archive"]["sha256"]
            and sha256_bytes(before_manifest) == helper["member_manifest"]["sha256"],
            "shared helper unsigned input closure differs")
    broker_paths = {row["path"] for row in final["files"]}
    relay_names = set(policy["files"]) - broker_paths
    require(len(relay_names) == 1, "shared helper policy does not identify exactly one relay")
    relay_name = next(iter(relay_names))
    before = {**helpers.archive_members(before_archive), relay_name: before_relay}
    after = {**helpers.archive_members(raw["broker.zip"]), relay_name: raw["relay.exe"]}
    checked_mapping, _ = helpers.verify_transform(before, after, policy,
        {p: helpers.canonical(value) for p, value in reports.items()}, architecture, relay_name)
    require(mapping == checked_mapping, "shared helper transform mapping differs")
    rebuilt_zip, rebuilt_manifest, rebuilt_mapping = helpers.finalize(
        raw["pre-signing-claim.json"], before, after, policy,
        {p: helpers.canonical(value) for p, value in reports.items()}, relay_path=relay_name,
        archive_path=helper["archive"]["path"], predecessor_catalog_sha256=final["predecessor_catalog_sha256"],
        input_archive=before_archive, input_manifest=before_manifest)
    require((rebuilt_zip, rebuilt_manifest, rebuilt_mapping) == (raw["broker.zip"], raw["broker-final-manifest.json"], raw["input-output.json"]),
            "shared helper finalization is not deterministic")
    closed = {"relay_sha256": sha256_bytes(raw["relay.exe"]), "archive_sha256": sha256_bytes(raw["broker.zip"]),
              "manifest_sha256": sha256_bytes(raw["broker-final-manifest.json"])}
    require(authorization["final_closure"] == closed
            and authorization["pre_signing_claim_sha256"] == auth["helper_claim_sha256"]
            and authorization["consumer_inputs"] == claim["consumer_inputs"]
            and authorization["mapping_sha256"] == sha256_bytes(raw["input-output.json"]),
            "attested helper output differs from exact measured closure")
    for consumer in helpers.pair(architecture):
        receipt = helpers.document(raw["receipt-" + consumer.split("-")[0] + ".json"])
        require(receipt == {"schema": 1, "profile": consumer, "input": claim["consumer_inputs"][consumer],
                            "broker_final_manifest_sha256": closed["manifest_sha256"],
                            "helper_closure_authorization_sha256": sha256_bytes(raw["helper-closure-authorization.json"])},
                "shared helper consumer receipt differs")
    outputs = {relay_path: raw["relay.exe"], archive_path: raw["broker.zip"],
               str(Path(archive_path).parent).replace("\\", "/") + "/broker-final-manifest.json": raw["broker-final-manifest.json"]}
    outputs.update({f"managed-helpers/{architecture}/{name}": content for name, content in raw.items()
                    if name not in ("relay.exe", "broker.zip")})
    return outputs, {"path": relay_path, **signing.identity(raw["relay.exe"])}, raw


def reseal_profile(root, auth, records, receipt, helper_records, *, profile_root=None, signature_reports=None):
    """Reseal native Windows or its separately verified WSL consumer tree."""
    windows = profile_root is None
    owned_root = root / "payload" if windows else profile_root
    cua_root = owned_root / "lib/cua"
    payload_raw = read_owned(cua_root, "payload.json")
    payload = parse_json(payload_raw)
    require(payload.get("schema") == 3, "profile reseal requires schema-3 input")
    profile = payload["release_profile"]
    require(profile.startswith("windows-" if windows else "wsl-"), "profile reseal consumer differs")
    if windows:
        files = signing.authorized(auth)
        expected_payload, _ = signing.original(records, auth)
        require(payload == expected_payload, "profile input payload changed")
        actual = signing.tree(root)
        require(set(actual) == set(files), "profile input file set changed")
        policy = auth["signing_policy"]["files"]
        native = {p for p, selected in policy.items() if selected["trust_class"] in ("publisher-sign", "vendor-preserve")}
        require(set(receipt) == native, "profile outer signer receipt file set differs")
        verify_outer_reports(receipt, signature_reports, policy)
        for path, before in files.items():
            if path in native:
                selected = policy[path]
                row = receipt[path]
                require(set(row) == {"input", "output", "trust_class", "signature_report_sha256"}
                        and row["input"] == before and row["output"] == actual[path]
                        and row["trust_class"] == selected["trust_class"]
                        and signing.valid_hash(row["signature_report_sha256"]), "profile outer signer receipt differs")
                if selected["trust_class"] == "vendor-preserve":
                    require(actual[path] == before, "profile vendor-preserve bytes changed")
            else:
                require(actual[path] == before, "unsigned profile input changed before helper insertion")
    else:
        # The coordinator independently verifies the immutable WSL artifact
        # before extraction. Never reconstruct its observation from Windows.
        require(not records.exists() and receipt == {} and signature_reports in (None, {}),
                "WSL reseal cannot consume an outer Windows signer receipt")
        files = signing.tree(owned_root)
        actual = dict(files)
        records.mkdir()
        (records / "pre-payload.json").write_bytes(payload_raw)
        (records / "pre-inventory.json").write_bytes(read_owned(cua_root, release.INVENTORY))
    outputs, relay, helper_raw = helper_outputs(cua_root, payload, auth, helper_records)
    before_inventory = parse_json(read_owned(records, "pre-inventory.json"))
    require(payload["installed_inventory_sha256"] == sha256_bytes(read_owned(records, "pre-inventory.json")),
            "profile input inventory differs")
    prefix = "payload/lib/cua/" if windows else "lib/cua/"
    owned_prefix = "payload/" if windows else ""
    if windows:
        all_native = {p for p in files if signing.native(p)}
        require(set(auth["signing_policy"]["files"]) == all_native - {prefix + relay["path"]},
                "shared helper must be the only native file omitted by the outer signer")
    changes = {prefix + path: data for path, data in outputs.items()}
    inventory = {**before_inventory, "files": {name: actual[prefix + name] for name in before_inventory["files"]}}
    for path, content in outputs.items():
        inventory["files"][path] = signing.identity(content)
    final_inventory = canonical_json(inventory)
    final_payload = canonical_json({**payload, "installed_inventory_sha256": sha256_bytes(final_inventory)})
    changes[prefix + release.INVENTORY] = final_inventory
    changes[prefix + "payload.json"] = final_payload
    generation = payload["cua_version"] + "-" + payload["requirements_sha256"][:12]
    if not windows:
        generation += "-unix-relative-v1"
    envelope = helpers.canonical({"schema": 1, "release_profile": profile, "cua_version": payload["cua_version"],
        "generation": generation, "payload_sha256": sha256_bytes(final_payload),
        "installed_inventory_sha256": sha256_bytes(final_inventory),
        "broker_final_manifest_sha256": sha256_bytes(helper_raw["broker-final-manifest.json"]),
        "helper_closure_authorization_sha256": sha256_bytes(helper_raw["helper-closure-authorization.json"]), "relay": relay})
    changes[owned_prefix + "cua-runtime-authorization.json"] = envelope
    mapping = {name: {"input": value, "output": actual[name], "operation":
                     "authenticode" if windows and name in receipt and receipt[name]["trust_class"] == "publisher-sign"
                     else "vendor-preserve" if windows and name in receipt else "unchanged"}
               for name, value in files.items()}
    for path, content in changes.items():
        mapping[path] = {"input": files.get(path), "output": signing.identity(content), "operation":
                         "inventory" if path == prefix + release.INVENTORY else
                         "payload-manifest" if path == prefix + "payload.json" else
                         "runtime-authorization" if path == owned_prefix + "cua-runtime-authorization.json" else "helper-closure"}
    # Persist the full exact transition evidence before replacing runtime files.
    for name, content in (("payload.json", final_payload), (release.INVENTORY, final_inventory),
                          ("input-output.json", canonical_json(mapping)), ("cua-runtime-authorization.json", envelope),
                          ("outer-signature-receipt.json", canonical_json(receipt)),
                          ("outer-signature-reports.json", helpers.canonical(signature_reports or {}))):
        require(not (records / name).exists(), "profile records already sealed")
        (records / name).write_bytes(content)
    helper_copy = records / "helper-records"
    helper_copy.mkdir()
    for name, content in helper_raw.items():
        (helper_copy / name).write_bytes(content)
    target_root = root if windows else owned_root
    for path, content in changes.items():
        target = target_root / path
        for parent in target.parents:
            if parent == target_root:
                break
            require(not parent.is_symlink() and not getattr(parent, "is_junction", lambda: False)(), "profile output parent is linked")
        require(not target.is_symlink(), "profile output is linked")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    binding = {key: payload[key] for key in ("target", "requirements_sha256", "wheel_manifest_sha256",
                                             "release_profile", "cua_profile_manifest_sha256")}
    final = release.validate_payload(cua_root, binding)
    return {"pre_signing": {**binding, "installed_inventory_sha256": payload["installed_inventory_sha256"]},
            "final": final, "hashes": {"cua/" + name: row["sha256"] for name, row in signing.tree(records).items()}}


def validate_records(records, auth):
    """Verify an archived Windows transition without trusting new mutable paths."""
    before, inventory = signing.original(records, auth)
    require(before["schema"] == 3, "profile records require schema 3")
    records_tree = signing.tree(records)
    expected_records = signing.NAMES | {"cua-runtime-authorization.json", "outer-signature-receipt.json", "outer-signature-reports.json"}
    expected_records |= {"helper-records/" + name for name in signing.HELPER_RECORDS}
    require(set(records_tree) == expected_records, "profile held record set differs")
    helper_root = records / "helper-records"
    verify_attestation(helper_root, auth)
    helper = {name: read_owned(helper_root, name) for name in signing.HELPER_RECORDS}
    claim = helpers.document(helper["pre-signing-claim.json"])
    require(sha256_bytes(helper["pre-signing-claim.json"]) == auth["helper_claim_sha256"]
            and sha256_bytes(helper["publisher-policy.json"]) == auth["helper_policy_sha256"],
            "profile held helper claim changed")
    final_manifest = helpers.document(helper["broker-final-manifest.json"])
    authorization = helpers.document(helper["helper-closure-authorization.json"])
    envelope_raw = read_owned(records, "cua-runtime-authorization.json")
    envelope = helpers.document(envelope_raw)
    require(envelope["release_profile"] == auth["cua_inputs"]["release_profile"]
            and envelope["cua_version"] == before["cua_version"]
            and envelope["generation"] == before["cua_version"] + "-" + before["requirements_sha256"][:12]
            and envelope["broker_final_manifest_sha256"] == sha256_bytes(helper["broker-final-manifest.json"])
            and envelope["helper_closure_authorization_sha256"] == sha256_bytes(helper["helper-closure-authorization.json"])
            and authorization["pre_signing_claim_sha256"] == auth["helper_claim_sha256"]
            and final_manifest["pre_signing_claim_sha256"] == auth["helper_claim_sha256"], "profile held runtime identity differs")
    relay = envelope["relay"]
    require({k: relay[k] for k in ("size", "sha256")} == signing.identity(helper["relay.exe"]),
            "profile held relay differs")
    architecture = claim["architecture"]
    suffix = f"computer_use/browser/winhost/{architecture}/vadgr-cua-host.exe"
    require(relay["path"].endswith(suffix), "profile held relay layout differs")
    package = relay["path"][:-len(suffix)]
    require(package == f"environments/{envelope['generation']}/Lib/site-packages/", "profile held package layout differs")
    archive_path = package + final_manifest["archive"]["path"]
    changes = {signing.PREFIX + relay["path"]: helper["relay.exe"], signing.PREFIX + archive_path: helper["broker.zip"],
               signing.PREFIX + str(Path(archive_path).parent).replace("\\", "/") + "/broker-final-manifest.json": helper["broker-final-manifest.json"],
               "payload/cua-runtime-authorization.json": envelope_raw}
    changes.update({signing.PREFIX + f"managed-helpers/{architecture}/{name}": raw for name, raw in helper.items()
                    if name not in ("relay.exe", "broker.zip")})
    raw_inventory, raw_payload = read_owned(records, release.INVENTORY), read_owned(records, "payload.json")
    changes[signing.PREFIX + release.INVENTORY] = raw_inventory
    changes[signing.PREFIX + "payload.json"] = raw_payload
    require(envelope["payload_sha256"] == sha256_bytes(raw_payload)
            and envelope["installed_inventory_sha256"] == sha256_bytes(raw_inventory)
            and raw_payload == canonical_json({**before, "installed_inventory_sha256": sha256_bytes(raw_inventory)}),
            "profile held metadata differs")
    mapping = parse_json(read_owned(records, "input-output.json"))
    receipt = parse_json(read_owned(records, "outer-signature-receipt.json"))
    verify_outer_reports(receipt, helpers.document(read_owned(records, "outer-signature-reports.json")), auth["signing_policy"]["files"])
    files = auth["files"]
    require(set(mapping) == set(files) | set(changes), "profile held transform file set differs")
    require(set(receipt) == set(auth["signing_policy"]["files"]), "profile held signer receipt differs")
    for path, row in mapping.items():
        require(set(row) == {"input", "output", "operation"} and row["input"] == files.get(path)
                and signing.valid_identity(row["output"]), "profile held mapping identity differs")
        if path in changes:
            require(row["output"] == signing.identity(changes[path]), "profile held helper or metadata mapping differs")
        elif path in receipt:
            selected = auth["signing_policy"]["files"][path]
            report = receipt[path]
            require(report["input"] == files[path] and report["output"] == row["output"]
                    and report["trust_class"] == selected["trust_class"]
                    and signing.valid_hash(report["signature_report_sha256"]), "profile held signature receipt differs")
            if selected["trust_class"] == "vendor-preserve":
                require(row["output"] == files[path], "profile held vendor bytes changed")
        else:
            require(row["output"] == files[path] and row["operation"] == "unchanged", "profile held unowned transform")
    expected_inventory = {**inventory, "files": {name.removeprefix(signing.PREFIX): row["output"]
        for name, row in mapping.items() if name.startswith(signing.PREFIX)
        and name not in (signing.PREFIX + "payload.json", signing.PREFIX + release.INVENTORY)}}
    require(raw_inventory == canonical_json(expected_inventory), "profile held inventory differs from exact outputs")
    return {"pre_signing": auth["cua_payload"], "final": {**auth["cua_inputs"], "installed_inventory_sha256": sha256_bytes(raw_inventory)},
            "hashes": {"cua/" + name: row["sha256"] for name, row in records_tree.items()}}
