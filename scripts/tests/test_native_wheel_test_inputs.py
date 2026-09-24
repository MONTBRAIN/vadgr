"""Native test inputs and skip identities remain closed and reviewable."""

import copy
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from scripts import build_native_wheels as build
from scripts import validate_native_wheels as gate


ROOT = Path(__file__).resolve().parents[2]


def descriptor():
    return gate.read_json(ROOT / "packaging/cua/native-wheels-input.json")


def report(policy):
    suite = ET.Element("testsuite")
    for index in range(policy["minimum_passed"]):
        ET.SubElement(suite, "testcase", classname="passed", name=str(index))
    for row in policy["skips"]:
        case = ET.SubElement(suite, "testcase", classname=row["classname"], name=row["name"])
        ET.SubElement(case, "skipped", message=row["reason"])
    return suite


@pytest.mark.parametrize("target,count", [("windows-aarch64", 30), ("macos-x86_64", 27)])
def test_reviewed_skips_bind_each_target_case_and_reason(target, count):
    policy = descriptor()["targets"][target]["test_policy"]
    assert len(policy["skips"]) == count
    counts = gate.test_counts(ET.tostring(report(policy)), policy)
    assert counts["skipped"] == count and counts["total"] == 4681
    assert len(counts["skip_cases"]) == count
    assert not any("root' option" in row["reason"] or "bcrypt exists" in row["reason"]
                   for row in policy["skips"])


@pytest.mark.parametrize("mutation", ["classname", "name", "reason", "duplicate", "extra", "missing", "uncollected"])
def test_native_skip_policy_refuses_case_substitution_or_collection_drift(mutation):
    policy = descriptor()["targets"]["macos-x86_64"]["test_policy"]
    suite = report(policy)
    case = suite[-1]
    if mutation in ("classname", "name"):
        case.set(mutation, "unreviewed")
    elif mutation == "reason":
        case[0].set("message", "unreviewed")
    elif mutation == "duplicate":
        suite[0] = copy.deepcopy(case)
    elif mutation == "extra":
        ET.SubElement(suite[0], "skipped", message=case[0].get("message"))
    elif mutation == "missing":
        case.remove(case[0])
    else:
        suite.remove(suite[0])
    with pytest.raises(gate.Refused):
        gate.test_counts(ET.tostring(suite), policy)


def test_test_inputs_are_pinned_and_reported_separately_from_shipped_components():
    data = descriptor()
    assert data["test_data"]["wycheproof"]["commit"] == "b61843a9a5115bb758134b6a1f5d5e502d445342"
    assert data["test_data"]["x509-limbo"]["commit"] == "341400395157bcd720afc37c8fdf026fcc7a88e9"
    for configuration in data["targets"].values():
        bcrypt = [row for row in configuration["python_dependencies"] if row["name"] == "bcrypt"]
        assert len(bcrypt) == 1 and bcrypt[0]["version"] == "5.0.0"
        assert set(data["test_data"]) <= set(gate.source_inputs(data, configuration))


@pytest.mark.parametrize("mutation", ["missing", "commit", "digest", "url", "bcrypt", "duplicate_case"])
def test_descriptor_refuses_incomplete_or_changed_test_inputs(mutation):
    data = copy.deepcopy(descriptor())
    if mutation == "missing":
        del data["test_data"]["wycheproof"]
    elif mutation in ("commit", "digest", "url"):
        data["test_data"]["wycheproof"][{"digest": "sha256"}.get(mutation, mutation)] = "unreviewed"
    elif mutation == "bcrypt":
        data["targets"]["windows-aarch64"]["python_dependencies"] = [
            row for row in data["targets"]["windows-aarch64"]["python_dependencies"] if row["name"] != "bcrypt"]
    else:
        cases = data["targets"]["macos-x86_64"]["test_policy"]["skips"]
        cases.append(copy.deepcopy(cases[0]))
    with pytest.raises(gate.Refused):
        gate.validate_descriptor(data)


def test_native_test_command_requires_both_populated_data_roots(tmp_path):
    data = descriptor()
    with pytest.raises(gate.Refused):
        build.test_arguments(tmp_path, data)
    for key, row in data["test_data"].items():
        root = tmp_path / key / (key + "-" + row["commit"])
        root.mkdir(parents=True)
        if key == "wycheproof":
            (root / "testvectors_v1").mkdir()
            (root / "testvectors_v1/aes_gcm_test.json").write_text('{"testGroups": [{}]}')
        else:
            (root / "limbo.json").write_text('{"testcases": [{}]}')
    arguments = build.test_arguments(tmp_path, data)
    assert len(arguments) == 2
    assert arguments[0].startswith("--wycheproof-root=")
    assert arguments[1].startswith("--x509-limbo-root=")


WINDOWS_MMAP_CASES = [
    {"classname": "tests.hazmat.primitives.test_aead." + name, "name": "test_data_too_large",
     "reason": "mmap and 64-bit platform required"}
    for name in ("TestChaCha20Poly1305", "TestAESCCM", "TestAESGCM", "TestAESOCB3", "TestAESSIV", "TestAESGCMSIV")
] + [{"classname": "tests.hazmat.primitives.test_ciphers", "name": "test_update_auto_chunking", "reason": "mmap required"}]


def test_only_windows_excludes_the_seven_upstream_unix_mmap_cases():
    data = descriptor()
    windows = data["targets"]["windows-aarch64"]["test_policy"]
    macos = data["targets"]["macos-x86_64"]["test_policy"]
    observed = [row for row in windows["skips"] if "mmap" in row["reason"]]
    assert observed == WINDOWS_MMAP_CASES
    assert windows["minimum_passed"] == 4651 and len(windows["skips"]) == 30
    assert macos["minimum_passed"] == 4654 and len(macos["skips"]) == 27
    assert not any("mmap" in row["reason"] for row in macos["skips"])
    assert not any("malloc_failure" in row["name"] for row in windows["skips"])


@pytest.mark.parametrize("expected", WINDOWS_MMAP_CASES)
@pytest.mark.parametrize("field", ["classname", "name", "reason", "missing", "duplicate"])
def test_windows_mmap_skip_requires_its_exact_reviewed_identity(expected, field):
    policy = descriptor()["targets"]["windows-aarch64"]["test_policy"]
    assert expected in policy["skips"]
    suite = report(policy)
    case = next(case for case in suite if case.get("classname") == expected["classname"]
                and case.get("name") == expected["name"])
    if field == "reason":
        case[0].set("message", "mmap is unavailable for an unrelated reason")
    elif field == "missing":
        case.remove(case[0])
    elif field == "duplicate":
        suite[0] = copy.deepcopy(case)
    else:
        case.set(field, "different_test")
    with pytest.raises(gate.Refused):
        gate.test_counts(ET.tostring(suite), policy)
