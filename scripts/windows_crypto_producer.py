"""Retain exact upstream x64 source/wheel artifacts and their producer records.

This is primary upstream build evidence, not a signing or legal approval.
"""

import argparse
import io
import json
from pathlib import Path
import subprocess
import zipfile

if __package__:
    from scripts.validate_package_inputs import canonical_json, read_owned, require, sha256_bytes
else:
    from validate_package_inputs import canonical_json, read_owned, require, sha256_bytes

REPOSITORY = "pyca/cryptography"
SOURCE = "ffde75a2b594822c740a2e4748b56c00548302bf"
RUN = 32890072935
JOB = 97940032724
FOLDER = "upstream-cryptography-50.0.1-x64"
ARTIFACTS = {
    "source": {"id": 9579112829, "name": "cryptography-sdist",
        "zip_sha256": "b3aebca66a48838d24aebac66ef4e0f49037afe24f34e38836763c4b7169d7bd",
        "member": "cryptography-50.0.1.tar.gz", "member_sha256": "5dd9bda1c12b4162f6ff568eeb5e0ff956c28d14406e875cfe8a63a2d414ff20"},
    "wheel": {"id": 9579199730, "name": "cryptography--win64-3.14-py311",
        "zip_sha256": "756eff5b659a9befe61c1f98cbd12215d3826b96ba4d2cd58b61c25dd9a949c8",
        "member": "cryptography-50.0.1-cp311-abi3-win_amd64.whl",
        "member_sha256": "aed8db4f6d71c51efb89530e12d9464e7bf2923d46c3205dc794a2a93f8c0648"},
}
SOURCES = {"workflow.yml.txt": ".github/workflows/wheel-builder.yml",
           "windows-action.yml.txt": ".github/actions/windows-wheel/action.yml"}
SOURCE_HASHES = {"workflow.yml.txt": "f7566e44970db9e4d8409e4c6a0aba51bd6d2a4abf6db0cba03254cba1ec039d",
                 "windows-action.yml.txt": "19bb5698ce119146ebdae890e72204175db79ae74ef4f6c00757c33b80cdce8b"}


def api(path, raw=False):
    arguments = ["gh", "api", "repos/" + REPOSITORY + "/" + path]
    if raw:
        arguments += ["-H", "Accept: application/vnd.github.raw+json"]
    result = subprocess.run(arguments, capture_output=True, timeout=120, check=False)
    require(result.returncode == 0 and len(result.stdout) < 32 * 1024 * 1024, "upstream producer retrieval failed")
    return result.stdout


def collect(output):
    require(not output.exists(), "upstream producer output already exists")
    files = {"run.json": api(f"actions/runs/{RUN}"), "job.json": api(f"actions/jobs/{JOB}")}
    for key, expected in ARTIFACTS.items():
        files[key + "-artifact.json"] = api(f"actions/artifacts/{expected['id']}")
        files[key + ".zip"] = api(f"actions/artifacts/{expected['id']}/zip")
    for name, path in SOURCES.items():
        files[name] = api("contents/" + path + "?ref=" + SOURCE, raw=True)
    validate_files(files)
    output.mkdir(parents=True)
    for name, raw in files.items():
        (output / name).write_bytes(raw)
    print(json.dumps({name: sha256_bytes(raw) for name, raw in sorted(files.items())}, sort_keys=True))


def validate_files(files):
    run, job = json.loads(files["run.json"]), json.loads(files["job.json"])
    require(run["id"] == RUN and run["head_sha"] == SOURCE and run["head_branch"] == "50.0.1"
            and run["repository"]["full_name"] == REPOSITORY and run["event"] == "push"
            and run["conclusion"] == "success" and run["path"] == SOURCES["workflow.yml.txt"], "upstream source run differs")
    require(job["id"] == JOB and job["run_id"] == RUN and job["head_sha"] == SOURCE
            and job["name"] == "3.14 win64 py311" and job["conclusion"] == "success", "upstream native job differs")
    for key, expected in ARTIFACTS.items():
        record = json.loads(files[key + "-artifact.json"])
        producer = record["workflow_run"]
        require(record["id"] == expected["id"] and record["name"] == expected["name"]
                and record["digest"] == "sha256:" + expected["zip_sha256"]
                and producer["id"] == RUN and producer["head_sha"] == SOURCE
                and producer["repository_id"] == producer["head_repository_id"] == 11939484, "upstream artifact producer differs")
        raw = files[key + ".zip"]
        require(sha256_bytes(raw) == expected["zip_sha256"], "upstream artifact bytes differ")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            require(archive.namelist() == [expected["member"]] and archive.infolist()[0].file_size < 16 * 1024 * 1024,
                    "upstream artifact member set differs")
            require(sha256_bytes(archive.read(expected["member"])) == expected["member_sha256"], "upstream source or wheel differs")
    require(all(sha256_bytes(files[name]) == expected for name, expected in SOURCE_HASHES.items()),
            "upstream source-to-wheel procedure differs")
    return {"schema": 1, "status": "upstream-source-observations-not-approval", "candidate_approval": False,
        "publishable": False, "repository": REPOSITORY, "source_commit": SOURCE, "run_id": RUN, "job_id": JOB,
        "artifacts": ARTIFACTS, "evidence_files": {name: sha256_bytes(raw) for name, raw in sorted(files.items())},
        "basis": "Upstream native job consumes the exact source artifact; its retained wheel equals the observed installed wheel.",
        "limitation": "Primary GitHub API records and exact artifact equality, not a new independently verified build attestation, reproducible rebuild or legal approval."}


def retain_in_packet(packet, archive_root, architecture):
    if architecture != "x64":
        return
    root = archive_root / FOLDER
    names = {"run.json", "job.json", *SOURCES,
             *(key + suffix for key in ARTIFACTS for suffix in (".zip", "-artifact.json"))}
    files = {name: read_owned(root, name) for name in sorted(names)}
    record = validate_files(files)
    source = next(row for row in packet.components if row["id"] == "native-cryptography")
    wheel = next(row for row in packet.components if row["id"] == "wheel-cryptography-50.0.1")
    observed = next(row for row in packet.evidence if row["id"] == wheel["id"])["observed_native_members"]
    require(source["sha256"] == ARTIFACTS["source"]["member_sha256"]
            and wheel["sha256"] == ARTIFACTS["wheel"]["member_sha256"] and observed, "observed upstream native wheel differs")
    record["observed_native_members"] = observed
    prefix = "producer-evidence/" + FOLDER + "/"
    for name, raw in files.items():
        packet.put(prefix + name, raw)
    path = "legal/NOTICES/native-cryptography/upstream-source-binding.json"
    raw = canonical_json(record)
    packet.put(path, raw)
    source["notice_files"].append({"path": path, "sha256": sha256_bytes(raw)})
    evidence = next(row for row in packet.evidence if row["id"] == source["id"])
    evidence.update(scope="native-source-bound-by-exact-upstream-run-artifacts", binary_mapping=record)
    pending = next(row for row in packet.pending if row["id"] == source["id"])
    pending["items"] = [item for item in pending["items"] if item != "target-binary-to-source-mapping"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    collect(parser.parse_args().output)
