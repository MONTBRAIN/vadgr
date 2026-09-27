#!/usr/bin/env python3
"""Verify unsigned CI payload assembly separately from runtime authorization."""

import argparse
import os
from pathlib import Path
import sys

if __package__:
    from scripts import cua_profiles as profiles, cua_release_inputs as release
    from scripts.validate_package_inputs import PackageInputError, parse_json, read_owned, require
else:
    import cua_profiles as profiles
    import cua_release_inputs as release
    from validate_package_inputs import PackageInputError, parse_json, read_owned, require


def expected_ready(root, source, trusted, profile):
    cua = root / "lib/cua"
    payload = parse_json(read_owned(cua, "payload.json"))
    if not profile:
        require(payload.get("schema") in (1, 2) and "release_profile" not in payload,
                "profile payload requires an explicit CI profile selection")
        return True
    binding, _, catalog = profiles.reviewed(source, trusted, profile)
    release.validate_payload(cua, binding)
    require(payload.get("cua_version") == catalog["cua_version"],
            "assembled CUA version differs from the reviewed profile")
    for name in ("cua-runtime-authorization.json", "cua-runtime-authorization.sigstore.json"):
        path = root / name
        require(not path.exists() and not path.is_symlink(),
                "unsigned CI payload unexpectedly contains installed authorization")
    # The daemon must refuse a profiled runtime until the protected producer
    # supplies the installed authorization. A complete inventory alone is not it.
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--trusted", type=Path, required=True)
    parser.add_argument("--github-env", type=Path, required=True)
    args = parser.parse_args()
    try:
        ready = expected_ready(args.root.resolve(), args.source.resolve(), args.trusted.resolve(),
                               os.environ.get("VADGR_RELEASE_PROFILE"))
        with args.github_env.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"CUA_CLEAN_EXPECTED_READY={str(ready).lower()}\n")
    except (PackageInputError, OSError, ValueError, KeyError, TypeError):
        print("CI payload verification failed; no readiness expectation is available.", file=sys.stderr)
        return 1
    print("CUA runtime availability is required." if ready else
          "Exact CUA profile and inventory verified. Unsigned runtime must remain unavailable; "
          "authorized CUA startup is not tested in this job.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
