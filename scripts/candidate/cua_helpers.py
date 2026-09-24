"""One shared native/WSL helper signing unit per architecture.

This is data-only trusted tooling. It does not sign, approve legal inputs or
assert native verification. Reports must be produced by the protected signer
after independent SignTool and Authenticode verification, not by the build.
"""

from __future__ import annotations

import io
import json
import re
import struct
import zipfile

if __package__ == "scripts.candidate":
    from scripts.cua_wheelhouse import archive_members, binary_architecture
    from scripts.validate_package_inputs import (
        PackageInputError, parse_json, relative_path, require, sha256_bytes, valid_hash,
    )
else:
    from cua_wheelhouse import archive_members, binary_architecture
    from validate_package_inputs import (
        PackageInputError, parse_json, relative_path, require, sha256_bytes, valid_hash,
    )

MAX_RECORD = 4 * 1024 * 1024
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
POLICY_KEYS = {"input_sha256", "trust_class", "signer_policy_sha256", "legal_approval_sha256",
               "signer", "certificate_sha256", "chain_root_sha256", "digest_algorithm", "timestamp_algorithm"}
REPORT_KEYS = {"schema", "file_sha256", "trust_class", "signer", "certificate_sha256", "chain_root_sha256",
               "digest_algorithm", "timestamp_algorithm", "signer_policy_sha256", "legal_approval_sha256",
               "signtool_exit", "authenticode_status", "chain_valid", "timestamp_valid"}


def canonical(value):
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False) + "\n").encode("utf-8")
    require(len(raw) <= MAX_RECORD, "helper record exceeds limit")
    return raw


def document(raw):
    require(0 < len(raw) <= MAX_RECORD, "helper record exceeds limit")
    value = parse_json(raw)
    require(canonical(value) == raw, "helper record is not canonical")
    return value


def digest(value):
    require(valid_hash(value) and value != "0" * 64, "missing exact helper digest")
    return value


def pair(architecture):
    require(architecture in ("x86_64", "aarch64"), "unsupported helper architecture")
    return ["windows-" + architecture, "wsl-" + architecture]


def closure(manifest):
    helper = manifest["helpers"]
    return {"relay_sha256": helper["relay"]["sha256"], "archive_sha256": helper["archive"]["sha256"],
            "manifest_sha256": helper["member_manifest"]["sha256"]}


def validate_policy(policy, files, architecture, relay_path):
    """Unknown/native-as-data classes fail before a paid operation is reserved."""
    require(isinstance(policy, dict) and set(policy) == {"schema", "files"} and type(policy["schema"]) is int
            and policy["schema"] == 1 and set(policy["files"]) == set(files), "helper policy file set differs")
    require(relay_path in files, "helper relay absent")
    folded = set()
    signing = []
    for path, data in files.items():
        relative_path(path)
        require(path.casefold() not in folded and path.split("/")[-1] != "broker-final-manifest.json",
                "helper paths collide or contain final manifest")
        folded.add(path.casefold())
        row = policy["files"][path]
        require(isinstance(row, dict) and set(row) == POLICY_KEYS and row["input_sha256"] == sha256_bytes(data),
                "helper policy does not bind exact input")
        native = data.startswith(b"MZ")
        if native:
            require(binary_architecture(data) == ("pe", architecture), "helper PE architecture differs")
        require(row["trust_class"] in ("publisher-sign", "vendor-preserve", "data"), "unknown helper trust class")
        if row["trust_class"] == "data":
            require(not native and not path.lower().endswith((".exe", ".dll", ".pyd"))
                    and all(row[k] is None for k in POLICY_KEYS - {"input_sha256", "trust_class"}),
                    "executable cannot be treated as data")
        else:
            require(native and all(digest(row[k]) for k in ("signer_policy_sha256", "legal_approval_sha256",
                                                           "certificate_sha256", "chain_root_sha256"))
                    and isinstance(row["signer"], str) and row["signer"]
                    and row["digest_algorithm"] == "sha256" and row["timestamp_algorithm"] == "rfc3161-sha256",
                    "helper signing identity or legal approval absent")
        if row["trust_class"] == "publisher-sign":
            # Publisher signing is an approved unsigned-input transformation,
            # never permission to remove or replace an upstream signature.
            pe_content(data, architecture)
            optional = struct.unpack_from("<I", data, 60)[0] + 24
            require(struct.unpack_from("<II", data, optional + 144) == (0, 0),
                    "publisher-sign input already has a certificate table")
            signing.append(path)
    require(policy["files"][relay_path]["trust_class"] == "publisher-sign", "relay must be publisher-signed")
    return sorted(signing, key=lambda p: p.encode("utf-8"))


def prepare(request, manifests, files, policy, relay_path, *, input_archive, input_manifest):
    """Build the exact pre-signing claim; the protected durable claim spends it."""
    require(set(request) == {"architecture", "cua_version", "source_commit", "tooling_commit", "consumer_inputs",
                              "legal_policy_sha256", "signing_run_id", "signing_job_id"}, "helper request schema differs")
    profiles = pair(request["architecture"])
    require(set(manifests) == set(profiles) and set(request["consumer_inputs"]) == set(profiles),
            "both Windows and WSL consumers must authorize the common closure")
    for profile, value in manifests.items():
        require(value["release_profile"] == profile and value["cua_version"] == request["cua_version"]
                and value["source_commit"] == request["source_commit"], "helper consumer manifest identity differs")
        binding = request["consumer_inputs"][profile]
        require(set(binding) == {"candidate_sha256", "catalog_sha256", "lock_sha256", "wheel_sha256"}
                and all(digest(v) for v in binding.values()), "helper consumer input binding differs")
    common = closure(manifests[profiles[0]])
    require(common == closure(manifests[profiles[1]]) and all(digest(v) for v in common.values()),
            "native Windows and WSL helpers are not byte-identical")
    require(sha256_bytes(files[relay_path]) == common["relay_sha256"], "helper relay input differs")
    require(sha256_bytes(input_archive) == common["archive_sha256"]
            and sha256_bytes(input_manifest) == common["manifest_sha256"]
            and archive_members(input_archive) == {p: b for p, b in files.items() if p != relay_path},
            "helper archive members differ before signing")
    for key in ("source_commit", "tooling_commit"):
        require(isinstance(request[key], str) and re.fullmatch(r"[0-9a-f]{40}", request[key])
                and request[key] != "0" * 40, "exact helper source identity absent")
    require(type(request["signing_run_id"]) is int and request["signing_run_id"] > 0
            and isinstance(request["signing_job_id"], str) and request["signing_job_id"], "signing job identity absent")
    digest(request["legal_policy_sha256"])
    paths = validate_policy(policy, files, request["architecture"], relay_path)
    # Consumer jobs do not change this key: native and WSL cannot reserve the
    # same closure under different profile-specific signing claims.
    closure_id = sha256_bytes(canonical({"architecture": request["architecture"], "input_closure": common}))
    return {"schema": 1, **request, "helper_closure_id": closure_id, "input_closure": common,
            "publisher_policy_sha256": sha256_bytes(canonical(policy)),
            "signing_claim_ref": "refs/tags/cua-signing-claims/" + closure_id,
            "signing_attempt": 1, "publisher_sign_paths": paths, "signing_operations": len(paths),
            "adoption_inputs": [common]}


def pe_content(data, architecture):
    """Normalize only the PE checksum/security-directory and appended certificate."""
    require(binary_architecture(data) == ("pe", architecture), "PE identity differs")
    offset = struct.unpack_from("<I", data, 60)[0]
    require(offset + 24 <= len(data), "truncated PE header")
    sections, optional_size = struct.unpack_from("<H", data, offset + 6)[0], struct.unpack_from("<H", data, offset + 20)[0]
    optional = offset + 24
    require(optional_size >= 152 and optional + optional_size + sections * 40 <= len(data)
            and struct.unpack_from("<H", data, optional)[0] == 0x20B, "invalid PE optional header")
    security = optional + 144
    certificate_offset, certificate_size = struct.unpack_from("<II", data, security)
    end = len(data)
    if certificate_size or certificate_offset:
        require(certificate_offset % 8 == 0 and certificate_offset > optional + optional_size
                and certificate_size >= 8 and certificate_offset + certificate_size == len(data),
                "PE certificate table is not bounded appended data")
        end = certificate_offset
        position = certificate_offset
        while position < len(data):
            require(position + 8 <= len(data), "truncated PE certificate")
            length, revision, kind = struct.unpack_from("<IHH", data, position)
            require(length >= 8 and revision == 0x200 and kind == 2 and position + length <= len(data),
                    "invalid PE certificate")
            position += (length + 7) & ~7
        require(position == len(data), "PE certificate padding differs")
    for index in range(sections):
        section = optional + optional_size + index * 40
        size, pointer = struct.unpack_from("<II", data, section + 16)
        require(pointer + size <= end, "PE section overlaps certificate")
    result = bytearray(data[:end])
    result[optional + 64:optional + 68] = b"\0" * 4
    result[security:security + 8] = b"\0" * 8
    return bytes(result)


def verify_transform(inputs, final, policy, reports, architecture, relay_path):
    paths = validate_policy(policy, inputs, architecture, relay_path)
    require(set(final) == set(inputs), "signed helper file set differs")
    signed = {p for p, r in policy["files"].items() if r["trust_class"] != "data"}
    require(set(reports) == signed, "independent helper signature reports differ")
    mapping = []
    for path, before in sorted(inputs.items(), key=lambda pair: pair[0].encode("utf-8")):
        row, after = policy["files"][path], final[path]
        report_hash = None
        if row["trust_class"] == "publisher-sign":
            original, transformed = pe_content(before, architecture), pe_content(after, architecture)
            padding = (-len(original)) % 8
            require(transformed == original or transformed == original + b"\0" * padding,
                    "signing changed executable code, data or overlay")
        else:
            require(before == after, "vendor-preserve or data bytes changed")
        if path in signed:
            report = document(reports[path])
            require(set(report) == REPORT_KEYS and type(report["schema"]) is int and report["schema"] == 1
                    and report["file_sha256"] == sha256_bytes(after)
                    and type(report["signtool_exit"]) is int and report["signtool_exit"] == 0
                    and report["authenticode_status"] == "Valid" and report["chain_valid"] is True
                    and report["timestamp_valid"] is True
                    and all(report[k] == row[k] for k in POLICY_KEYS - {"input_sha256"}),
                    "independent signature report does not satisfy approved policy")
            report_hash = sha256_bytes(reports[path])
        mapping.append({"path": path, "input_sha256": sha256_bytes(before), "sha256": sha256_bytes(after),
                        "size": len(after), "trust_class": row["trust_class"], "signature_report_sha256": report_hash})
    return {"schema": 1, "files": mapping}, paths


def deterministic_archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for path, data in sorted(files.items(), key=lambda pair: pair[0].encode("utf-8")):
            relative_path(path)
            info = zipfile.ZipInfo(path, FIXED_TIME)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    raw = output.getvalue()
    require(archive_members(raw) == files, "deterministic helper archive validation failed")
    return raw


def finalize(claim_raw, inputs, final, policy, reports, *, relay_path, archive_path,
             predecessor_catalog_sha256, input_archive, input_manifest):
    """Freeze manifest after signing, before authorization/artifact allocation."""
    claim = document(claim_raw)
    digest(predecessor_catalog_sha256)
    relative_path(archive_path)
    require(sha256_bytes(input_archive) == claim["input_closure"]["archive_sha256"]
            and sha256_bytes(input_manifest) == claim["input_closure"]["manifest_sha256"]
            and archive_members(input_archive) == {p: b for p, b in inputs.items() if p != relay_path},
            "helper input archive member closure differs")
    require(sha256_bytes(canonical(policy)) == claim["publisher_policy_sha256"], "helper trust policy changed")
    mapping, signing_paths = verify_transform(inputs, final, policy, reports, claim["architecture"], relay_path)
    require(claim["signing_attempt"] == 1 and claim["publisher_sign_paths"] == signing_paths
            and claim["signing_operations"] == len(signing_paths), "helper signing claim differs")
    archive = deterministic_archive({p: b for p, b in final.items() if p != relay_path})
    rows = []
    for row in mapping["files"]:
        if row["path"] == relay_path:
            continue
        selected = policy["files"][row["path"]]
        rows.append({**row, "role": "browser-broker", "execution_os": "windows", "architecture": claim["architecture"],
                     "signer_policy_sha256": selected["signer_policy_sha256"],
                     "legal_approval_sha256": selected["legal_approval_sha256"]})
    # Both consumers use the same pre-publication catalog, not another inferred
    # output or a later receipt hash (which would create a digest cycle).
    catalogs = {b["catalog_sha256"] for b in claim["consumer_inputs"].values()}
    require(len(catalogs) == 1, "shared helper consumers use different input catalogs")
    manifest = {"schema": 1, "mode": "managed-signed", "consumer_profiles": pair(claim["architecture"]),
                **{k: claim[k] for k in ("cua_version", "architecture", "helper_closure_id", "source_commit", "tooling_commit",
                                        "consumer_inputs", "signing_claim_ref", "signing_run_id", "signing_attempt",
                                        "signing_job_id", "publisher_policy_sha256")},
                "input_catalog_sha256": next(iter(catalogs)), "input_manifest_sha256": sha256_bytes(input_manifest),
                "input_archive_sha256": sha256_bytes(input_archive), "pre_signing_claim_sha256": sha256_bytes(claim_raw),
                "archive": {"path": archive_path, "size": len(archive), "sha256": sha256_bytes(archive)},
                "files": rows, "predecessor_catalog_sha256": predecessor_catalog_sha256}
    return archive, canonical(manifest), canonical(mapping)


def authorize(claim_raw, manifest_raw, mapping_raw, relay, artifact, ledger, *, observed_consumers):
    """After immutable upload, emit the attestation subject and both receipts."""
    claim, manifest = document(claim_raw), document(manifest_raw)
    mapping = document(mapping_raw)
    require(set(mapping) == {"schema", "files"} and mapping["schema"] == 1, "helper mapping schema differs")
    expected_ledger = [{"pre_signing_claim_sha256": sha256_bytes(claim_raw),
                        "helper_closure_id": claim["helper_closure_id"], "operations": claim["signing_operations"]}]
    require(ledger == expected_ledger and manifest["pre_signing_claim_sha256"] == sha256_bytes(claim_raw),
            "shared helper signing was not consumed exactly once")
    require(manifest["schema"] == 1 and manifest["mode"] == "managed-signed"
            and manifest["consumer_profiles"] == pair(claim["architecture"])
            and all(manifest[k] == claim[k] for k in ("helper_closure_id", "architecture", "cua_version",
                "source_commit", "tooling_commit", "consumer_inputs", "signing_claim_ref", "signing_run_id",
                "signing_attempt", "signing_job_id", "publisher_policy_sha256"))
            and manifest["input_archive_sha256"] == claim["input_closure"]["archive_sha256"]
            and manifest["input_manifest_sha256"] == claim["input_closure"]["manifest_sha256"],
            "shared helper final manifest differs from prior claim")
    mapped = {row["path"]: row for row in mapping["files"]}
    require(len(mapped) == len(mapping["files"]), "helper mapping repeats a member")
    broker_paths = {row["path"] for row in manifest["files"]}
    require(len(broker_paths) == len(manifest["files"]) and len(set(mapped) - broker_paths) == 1,
            "helper mapping does not identify exactly one relay")
    for row in manifest["files"]:
        require(row["path"] in mapped and all(mapped[row["path"]][k] == row[k]
                for k in ("input_sha256", "sha256", "size", "trust_class", "signature_report_sha256")),
                "helper mapping and final member inventory differ")
    relay_mapping = mapped[next(iter(set(mapped) - broker_paths))]
    require(relay_mapping["input_sha256"] == claim["input_closure"]["relay_sha256"]
            and relay_mapping["sha256"] == sha256_bytes(relay) and relay_mapping["size"] == len(relay),
            "helper mapped relay differs")
    final = {"relay_sha256": sha256_bytes(relay), "archive_sha256": manifest["archive"]["sha256"],
             "manifest_sha256": sha256_bytes(manifest_raw)}
    require(observed_consumers == {profile: final for profile in pair(claim["architecture"])},
            "both independently observed consumers must contain the exact shared signed closure")
    require(set(artifact) == {"id", "sha256", "subjects"} and type(artifact["id"]) is int and artifact["id"] > 0
            and digest(artifact["sha256"]) and artifact["subjects"] == {**final, "mapping_sha256": sha256_bytes(mapping_raw)},
            "immutable shared helper output artifact binding differs")
    authorization = {"schema": 1, "pre_signing_claim_sha256": sha256_bytes(claim_raw),
                     **{k: claim[k] for k in ("helper_closure_id", "architecture", "cua_version", "source_commit", "tooling_commit",
                                             "input_closure", "consumer_inputs", "signing_run_id", "signing_attempt",
                                             "signing_job_id", "publisher_policy_sha256", "legal_policy_sha256")},
                     "final_closure": final, "output_artifact": artifact, "mapping_sha256": sha256_bytes(mapping_raw),
                     "adoption_edges": [{"direction": "unsigned-to-signed", "architecture": claim["architecture"],
                                         "cua_version": claim["cua_version"], "source_commit": claim["source_commit"],
                                         "input_closure": claim["input_closure"], "final_closure": final}]}
    raw = canonical(authorization)
    receipts = {profile: canonical({"schema": 1, "profile": profile, "input": claim["consumer_inputs"][profile],
                                    "broker_final_manifest_sha256": sha256_bytes(manifest_raw),
                                    "helper_closure_authorization_sha256": sha256_bytes(raw)})
                for profile in pair(claim["architecture"])}
    return raw, receipts
