#!/usr/bin/env python3
"""Build the reviewed Windows outer-signing records from exact preparation inputs.

This tool does not sign, authorize a protected operation, or create a release.
It converts a measured native-file ledger and the reviewed package-input record
into two deterministic records. The review record is the named source for the
signer-policy digest. The outer policy binds that digest and the exact package
review digest into every native-file decision.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.candidate import cua_helpers as helpers
from scripts.validate_package_inputs import (
    PackageInputError,
    parse_json,
    read_owned,
    require,
)

PUBLISHER = {
    "signer": "CN=Victor Santiago Montaño Diaz,O=Victor Santiago Montaño Diaz,L=Pasto,ST=Nariño,C=CO",
    "certificate_sha256": "2dba70db8174b6fab9002ed906c0076e5321c5be82c9b4b6c1775456fef90d22",
    "chain_root_sha256": "85666a562ee0be5ce925c1d8890a6f76a87ec16d4d7d5f29ea7419cf20123b69",
}

VENDOR = {
    "x86_64": {
        "payload/lib/cua/python/3.12.14/vcruntime140.dll": {
            "input_sha256": "d5e4d9a3e835fa679450145d6a7d94e36573a509317111904d9b3712c30d9066",
            "signer": "CN=Microsoft Windows Software Compatibility Publisher, O=Microsoft Corporation, L=Redmond, S=Washington, C=US",
            "certificate_sha256": "3fca21bb42a1f796c8535be8eec19e66823f5649c5f242bd81b4dd236e430a75",
            "chain_root_sha256": "847df6a78497943f27fc72eb93f9a637320a02b561d0a91b09e87a7807ed7c61",
        },
        "payload/lib/cua/python/3.12.14/vcruntime140_1.dll": {
            "input_sha256": "1f2d41c4aa5db0bc33ebf7b66d72943a817d7ce6cbe880502a9403823633093f",
            "signer": "CN=Microsoft Windows Software Compatibility Publisher, O=Microsoft Corporation, L=Redmond, S=Washington, C=US",
            "certificate_sha256": "3fca21bb42a1f796c8535be8eec19e66823f5649c5f242bd81b4dd236e430a75",
            "chain_root_sha256": "847df6a78497943f27fc72eb93f9a637320a02b561d0a91b09e87a7807ed7c61",
        },
        "payload/lib/cua/python/3.12.14/DLLs/tcl86t.dll": {
            "input_sha256": "fbfd065f861ec0a90dd513bc209c56bbc23c54d2839964a0ec2df95848af7860",
            "signer": "CN=Python Software Foundation, O=Python Software Foundation, L=Wolfeboro, S=New Hampshire, C=US",
            "certificate_sha256": "7793a3110357540ec2cadc9f5956ffe8965dbb50b37c35e9d42ae0282af440f6",
            "chain_root_sha256": "3e9099b5015e8f486c00bcea9d111ee721faba355a89bcf1df69561e3dc6325c",
        },
        "payload/lib/cua/python/3.12.14/DLLs/tk86t.dll": {
            "input_sha256": "cd2f60075064dfc2e65c88b239a970cb4bd07cb3eec7cc26fb1bf978d4356b08",
            "signer": "CN=Python Software Foundation, O=Python Software Foundation, L=Wolfeboro, S=New Hampshire, C=US",
            "certificate_sha256": "7793a3110357540ec2cadc9f5956ffe8965dbb50b37c35e9d42ae0282af440f6",
            "chain_root_sha256": "3e9099b5015e8f486c00bcea9d111ee721faba355a89bcf1df69561e3dc6325c",
        },
    },
    "aarch64": {
        "payload/lib/cua/python/3.12.14/vcruntime140.dll": {
            "input_sha256": "d8a8513921544569837e400d37cc71302819967ae6defa932266a7ecb41dbaf9",
            "signer": "CN=Microsoft Corporation, O=Microsoft Corporation, L=Redmond, S=Washington, C=US",
            "certificate_sha256": "58b5021c22dd86d7838350b38ec5a702b48634125acb6ded71022de07836f768",
            "chain_root_sha256": "847df6a78497943f27fc72eb93f9a637320a02b561d0a91b09e87a7807ed7c61",
        },
        "payload/lib/cua/python/3.12.14/DLLs/tcl86t.dll": {
            "input_sha256": "964af896e6ca85fb2648a16d285290360b09089b3c5cce92d401a5326be0d228",
            "signer": "CN=Python Software Foundation, O=Python Software Foundation, L=Beaverton, S=Oregon, C=US",
            "certificate_sha256": "6045e624888e299179d5ae0ceda57c9874ff6ccf889fa14b2d50f751bfb9e2f8",
            "chain_root_sha256": "552f7bdcf1a7af9e6ce672017f4f12abf77240c78e761ac203d1d9d20ac89988",
        },
        "payload/lib/cua/python/3.12.14/DLLs/tk86t.dll": {
            "input_sha256": "9b2f08cc10244ed9ccf4bc5770151c819e7e34d3a6c658a053734a63bb5c9e1a",
            "signer": "CN=Python Software Foundation, O=Python Software Foundation, L=Beaverton, S=Oregon, C=US",
            "certificate_sha256": "6045e624888e299179d5ae0ceda57c9874ff6ccf889fa14b2d50f751bfb9e2f8",
            "chain_root_sha256": "552f7bdcf1a7af9e6ce672017f4f12abf77240c78e761ac203d1d9d20ac89988",
        },
        "payload/lib/cua/python/3.12.14/tcl/dde1.4/tcldde14.dll": {
            "input_sha256": "eb2ebdb74bcba228d3e2ca5b98c2caafe95d4b3ca8b99e6f17b4c911b0084754",
            "signer": "CN=Python Software Foundation, O=Python Software Foundation, L=Beaverton, S=Oregon, C=US",
            "certificate_sha256": "6045e624888e299179d5ae0ceda57c9874ff6ccf889fa14b2d50f751bfb9e2f8",
            "chain_root_sha256": "552f7bdcf1a7af9e6ce672017f4f12abf77240c78e761ac203d1d9d20ac89988",
        },
        "payload/lib/cua/python/3.12.14/tcl/reg1.3/tclreg13.dll": {
            "input_sha256": "df5ef38d8d1e4495a805ce199c5e1eef12c49ec0a710d704c997f71742b484f8",
            "signer": "CN=Python Software Foundation, O=Python Software Foundation, L=Beaverton, S=Oregon, C=US",
            "certificate_sha256": "6045e624888e299179d5ae0ceda57c9874ff6ccf889fa14b2d50f751bfb9e2f8",
            "chain_root_sha256": "552f7bdcf1a7af9e6ce672017f4f12abf77240c78e761ac203d1d9d20ac89988",
        },
    },
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def finalize(ledger_raw: bytes, package_review_raw: bytes) -> tuple[bytes, bytes]:
    ledger = parse_json(ledger_raw)
    architecture = ledger.get("architecture")
    require(architecture in VENDOR and ledger.get("status") == "review-input-only"
            and ledger.get("signing_approved") is False and isinstance(ledger.get("files"), dict),
            "outer review ledger scope differs")
    package_review = parse_json(package_review_raw)
    require(package_review.get("status") == "approved"
            and package_review.get("target") == architecture + "-pc-windows-msvc"
            and package_review.get("version") == "0.5.0",
            "package review scope differs")
    vendor = VENDOR[architecture]
    require(set(vendor) <= set(ledger["files"]), "reviewed vendor file is absent")
    rows = {}
    for name, measured in sorted(ledger["files"].items()):
        helpers.digest(measured.get("input_sha256"))
        if name in vendor:
            selected = vendor[name]
            require(selected["input_sha256"] == measured["input_sha256"],
                    "reviewed vendor bytes differ")
            identity = {key: selected[key] for key in
                        ("signer", "certificate_sha256", "chain_root_sha256")}
            trust_class = "vendor-preserve"
        else:
            identity = PUBLISHER
            trust_class = "publisher-sign"
        rows[name] = {
            "input_sha256": measured["input_sha256"],
            "trust_class": trust_class,
            **identity,
            "digest_algorithm": "sha256",
            "timestamp_algorithm": "rfc3161-sha256",
        }
    review = {
        "schema": 1,
        "scope": "vadgr-0.5.0-windows-outer-signing",
        "architecture": architecture,
        "publisher": PUBLISHER,
        "files": rows,
    }
    review_raw = helpers.canonical(review)
    signer_policy_sha256 = sha256(review_raw)
    legal_approval_sha256 = sha256(package_review_raw)
    policy = {"schema": 1, "files": {name: {
        **row,
        "signer_policy_sha256": signer_policy_sha256,
        "legal_approval_sha256": legal_approval_sha256,
    } for name, row in rows.items()}}
    return review_raw, helpers.canonical(policy)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--package-review", type=Path, required=True)
    parser.add_argument("--review-out", type=Path, required=True)
    parser.add_argument("--policy-out", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        review, policy = finalize(read_owned(args.ledger.parent, args.ledger.name),
                                  read_owned(args.package_review.parent, args.package_review.name))
        for path, expected in ((args.review_out, review), (args.policy_out, policy)):
            if args.check:
                require(read_owned(path.parent, path.name) == expected, "generated signing record differs")
            else:
                require(not path.exists(), "signing record already exists")
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as stream:
                    stream.write(expected)
        print("Verified deterministic Windows outer-signing records. No signing operation was requested.")
        return 0
    except (OSError, PackageInputError):
        print("Windows signing record finalization refused.", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
