#!/usr/bin/env python3
"""Separate CI missing-input refusal checks from actual clean installation."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tomllib

if __package__:
    from scripts import cua_profiles as profiles, cua_release_inputs as release, prepare_cua_build as prepare
    from scripts.validate_package_inputs import PackageInputError, read_owned, require
else:
    import cua_profiles as profiles
    import cua_release_inputs as release
    import prepare_cua_build as prepare
    from validate_package_inputs import PackageInputError, read_owned, require


def check(source, trusted, target, output):
    package = tomllib.loads(read_owned(source, "Cargo.toml").decode("utf-8"))["package"]
    require(package.get("name") == "vadgr-daemon" and package.get("version") in ("0.4.12", "0.5.0"),
            "source package has no reviewed CI layout")
    require(target in release.TARGETS, "unsupported build host target")
    if package["version"] == "0.4.12":
        # Reviewed profile data can precede its product implementation on master.
        # The legacy source installers still run; this source cannot build schema 3.
        require(not any(os.environ.get(name) for name in (
            "VADGR_RELEASE_PROFILE", "VADGR_RELEASE_PAYLOAD_BUILD", "VADGR_BUILD_WHEELHOUSE")),
            "legacy source inherited a reviewed payload selection")
        require(not output.exists() and not output.is_symlink(), "unpromoted output already exists")
        return "unpromoted", {}
    profiled = any((root / profiles.INPUTS).exists() for root in (source, trusted))
    lock = profiles.lock_path(profiles.native_profile(target)) if profiled else release.lock_path(target)
    absent = all(not (root / lock).exists() and not (root / lock).is_symlink()
                 for root in (source, trusted))
    if absent and (source / release.MANIFEST).is_file() and (trusted / release.MANIFEST).is_file():
        for name in (release.MANIFEST, release.BUNDLE):
            require(read_owned(source, name) == read_owned(trusted, name),
                    "unpromoted target metadata differs from reviewed bytes")
        release.manifest(trusted)
        require(not output.exists() and not output.is_symlink(), "refusal output already exists")
        try:
            prepare.prepare(source, trusted, target, output, True)
        except PackageInputError:
            require(not output.exists() and not output.is_symlink(), "refusal mutated output")
            return "unpromoted", {}
        raise PackageInputError("unpromoted target did not refuse payload preparation")
    values = prepare.prepare(source, trusted, target, output, True)
    return "reviewed" if values else "development", values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--trusted", type=Path, required=True)
    parser.add_argument("--target")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--github-env", type=Path, required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        target = args.target
        if target is None:
            result = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True)
            target = next(line.removeprefix("host: ") for line in result.stdout.splitlines()
                          if line.startswith("host: "))
        mode, values = check(args.source.resolve(), args.trusted.resolve(), target,
                             args.out.parent.resolve() / args.out.name)
        require(all("\n" not in value and "\r" not in value for value in values.values()),
                "unsafe build environment value")
        with args.github_env.open("a", encoding="utf-8", newline="\n") as stream:
            for key, value in values.items():
                stream.write(f"{key}={value}\n")
        with args.github_output.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"mode={mode}\n")
    except (PackageInputError, OSError, ValueError, KeyError, TypeError, StopIteration, subprocess.SubprocessError):
        print("CI payload boundary failed; no install result is available.", file=sys.stderr)
        return 1
    print("Reviewed payload assembly is unavailable for this source. Clean installation: not run."
          if mode == "unpromoted" else f"CUA assembly mode: {mode}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
