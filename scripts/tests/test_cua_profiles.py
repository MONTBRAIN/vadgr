"""Synthetic format fixtures; these tests do not claim native signed evidence."""

import copy
import io
import struct
import zipfile

import pytest

from scripts import cua_profiles as profiles
from scripts import cua_wheelhouse as wheels
from scripts.validate_package_inputs import PackageInputError, sha256_bytes


def pe(arch="x86_64"):
    data = bytearray(128)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 64)
    data[64:68] = b"PE\0\0"
    struct.pack_into("<H", data, 68, 0x8664 if arch == "x86_64" else 0xAA64)
    return bytes(data)


def archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as stream:
        for path, data in files.items():
            stream.writestr(path, data)
    return output.getvalue()


def record(path, data, key="path"):
    return {key: path, "size": len(data), "sha256": sha256_bytes(data)}


def fixture(profile):
    system, arch = profile.split("-", 1)
    prefix = profiles.PREFIX
    files = {"computer_use/__init__.py": b""}
    executables = [{"release_profile": profile, "role": "runtime", "execution_os": "linux" if system == "wsl" else system,
                    "architecture": arch, "wheel_path": "computer_use/__init__.py", "archive_members": [],
                    "size": 0, "sha256": sha256_bytes(b""), "component": "vadgr-computer-use",
                    "consumer": "computer_use.mcp_server"}]
    archives, helper = [], None
    if system in ("windows", "wsl"):
        relay_path = prefix + f"winhost/{arch}/host.exe"
        zip_path = prefix + f"winbroker/{arch}/broker.zip"
        member_path = prefix + f"winbroker/{arch}/broker.manifest.json"
        nested = {"broker.exe": pe(arch), "LICENSE": b"fixture"}
        files.update({relay_path: pe(arch), zip_path: archive(nested), member_path: b"{}\n"})
        helper = {"architecture": arch, "relay": record(relay_path, files[relay_path]),
                  "archive": record(zip_path, files[zip_path]), "member_manifest": record(member_path, files[member_path])}
        # The independent expected inventory follows UTF-8 path order.
        executables.append({"release_profile": profile, "role": "browser-broker", "execution_os": "windows",
                            "architecture": arch, "wheel_path": zip_path, "archive_members": ["broker.exe"],
                            "size": len(nested["broker.exe"]), "sha256": sha256_bytes(nested["broker.exe"]),
                            "component": "browser-broker-runtime", "consumer": "computer_use.browser.windows_broker"})
        executables.append({"release_profile": profile, "role": "browser-relay", "execution_os": "windows",
                            "architecture": arch, "wheel_path": relay_path, "archive_members": [],
                            "size": len(files[relay_path]), "sha256": sha256_bytes(files[relay_path]),
                            "component": "vadgr-computer-use", "consumer": "computer_use.setup.extension_setup"})
        archives = [{"wheel_path": zip_path, "archive_members": [], "size": len(files[zip_path]),
                     "sha256": sha256_bytes(files[zip_path]),
                     "members": [record(p, b) for p, b in sorted(nested.items())]}]
    value = {"schema": 1, "cua_version": "0.7.9", "source_commit": "a" * 40, "release_profile": profile,
             "interpreter": {}, "files": [record(p, b, "wheel_path") for p, b in sorted(files.items())],
             "executables": executables, "archives": archives, "helpers": helper}
    return seal(files, value)


def seal(files, value):
    profile = value["release_profile"]
    raw = profiles.canonical(value)
    digest = sha256_bytes(raw)
    result = {p: b for p, b in files.items() if not p.endswith(("_profile_trust.py", "cua-profile-manifest.json"))}
    result[profiles.PREFIX + f"profiles/{profile}/cua-profile-manifest.json"] = raw
    trust = {"schema": 1, "mode": "managed", "release_profile": profile, "manifest_sha256": {profile: digest}}
    result[profiles.PREFIX + "_profile_trust.py"] = ("TRUST = " + repr(trust) + "\n").encode()
    return result, value, digest


@pytest.mark.parametrize("profile", profiles.PROFILES)
def test_all_eight_profile_inventories(profile):
    members, value, digest = fixture(profile)
    assert profiles.validate_members(members, profile, digest) == value


@pytest.mark.parametrize("mutation", ["extra", "changed", "missing", "role", "architecture", "unsigned-fallback"])
def test_profile_inventory_cannot_authorize_unreviewed_bytes(mutation):
    members, value, digest = fixture("wsl-x86_64")
    if mutation == "extra":
        members["extra.exe"] = pe()
    elif mutation == "changed":
        members[value["helpers"]["relay"]["path"]] = pe() + b"changed"
    elif mutation == "missing":
        del members[value["helpers"]["archive"]["path"]]
    elif mutation == "unsigned-fallback":
        members[profiles.PREFIX + "_profile_trust.py"] = b"TRUST = {'mode': 'standalone-input'}\n"
    else:
        value = copy.deepcopy(value)
        value["executables"][1][mutation] = "runtime" if mutation == "role" else "aarch64"
        members, value, digest = seal(members, value)
    with pytest.raises(PackageInputError):
        profiles.validate_members(members, "wsl-x86_64", digest)


@pytest.mark.parametrize("files", [{"A": b"x", "a/b": b"y"}, {"x.dll": b"x", "X.DLL": b"y"},
                                   {"../outside": b"x"}, {"CON.txt": b"x"}])
def test_archives_reject_aliases_and_unsafe_names(files):
    with pytest.raises(PackageInputError):
        wheels.archive_members(archive(files))


def test_profile_target_not_only_interpreter_platform():
    assert profiles.target_for("linux-x86_64") == profiles.target_for("wsl-x86_64")
    assert profiles.lock_path("linux-x86_64") != profiles.lock_path("wsl-x86_64")
    with pytest.raises(PackageInputError):
        profiles.target_for("windows-amd64")


def test_missing_promotion_never_falls_back(tmp_path):
    with pytest.raises(PackageInputError):
        profiles.reviewed(tmp_path, tmp_path, "windows-x86_64")
