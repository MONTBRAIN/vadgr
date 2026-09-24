"""Select explicit development assembly or materialize reviewed release inputs."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

if __package__:
    from scripts import cua_wheelhouse as wheels
    from scripts.validate_package_inputs import PackageInputError, require
else:
    import cua_wheelhouse as wheels
    from validate_package_inputs import PackageInputError, require


def prepare(source, trusted, target, output, allow_development):
    require(target in wheels.release.TARGETS, "unsupported build host target")
    names = (wheels.release.MANIFEST, wheels.release.BUNDLE, "packaging/cua/locks")
    present = any((root / name).exists() or (root / name).is_symlink()
                  for root in (source, trusted) for name in names)
    if allow_development and not present:
        require(not os.environ.get("VADGR_RELEASE_PAYLOAD_BUILD")
                and not os.environ.get("VADGR_BUILD_WHEELHOUSE"), "inherited release selection conflicts with development")
        return {}
    wheels.materialize(source, trusted, target, output)
    return {"VADGR_RELEASE_PAYLOAD_BUILD": "1", "VADGR_BUILD_WHEELHOUSE": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--trusted", type=Path, required=True)
    parser.add_argument("--target")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--github-env", type=Path, required=True)
    parser.add_argument("--allow-development", action="store_true")
    args = parser.parse_args()
    try:
        target = args.target
        if target is None:
            result = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True)
            target = next(line.removeprefix("host: ") for line in result.stdout.splitlines() if line.startswith("host: "))
        values = prepare(args.source.resolve(), args.trusted.resolve(), target,
                         args.out.parent.resolve() / args.out.name, args.allow_development)
        require(all("\n" not in value and "\r" not in value for value in values.values()),
                "unsafe build environment value")
        with args.github_env.open("a", encoding="utf-8", newline="\n") as stream:
            for key, value in values.items():
                stream.write(f"{key}={value}\n")
    except (PackageInputError, OSError, ValueError, KeyError, TypeError, StopIteration, subprocess.SubprocessError):
        print("CUA build preparation refused; reviewed inputs cannot fall back to development.", file=sys.stderr)
        return 1
    print("Reviewed offline CUA assembly prepared." if values else "Development CUA assembly selected; not a release qualification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
