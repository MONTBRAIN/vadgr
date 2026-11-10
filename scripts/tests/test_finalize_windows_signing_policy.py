"""The Windows outer policy must be derived from named, non-circular sources."""

import hashlib
import json

from scripts import finalize_windows_signing_policy as finalize


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def test_finalizer_binds_review_and_package_without_a_cycle(monkeypatch):
    monkeypatch.setattr(finalize, "VENDOR", {"x86_64": {}})
    ledger = canonical({"schema": 1, "status": "review-input-only", "signing_approved": False,
                        "architecture": "x86_64",
                        "files": {"payload/vadgr.exe": {"input_sha256": "a" * 64}}})
    package = canonical({"status": "approved", "target": "x86_64-pc-windows-msvc",
                         "version": "0.5.0"})
    review_raw, policy_raw = finalize.finalize(ledger, package)
    review = json.loads(review_raw)
    policy = json.loads(policy_raw)
    row = policy["files"]["payload/vadgr.exe"]
    assert review["files"]["payload/vadgr.exe"]["trust_class"] == "publisher-sign"
    assert row["signer_policy_sha256"] == hashlib.sha256(review_raw).hexdigest()
    assert row["legal_approval_sha256"] == hashlib.sha256(package).hexdigest()
    assert row["signer_policy_sha256"] != row["legal_approval_sha256"]
