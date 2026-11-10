"""Start the pinned cua module from vadgr's isolated private interpreter."""

from __future__ import annotations

import runpy
import os
import site
import sys


def _add_private_site_packages() -> None:
    """Use the sealed Windows packages without a build-root virtualenv launcher."""
    if os.name != "nt":
        return
    environments = os.path.join(os.path.dirname(os.path.abspath(__file__)), "environments")
    candidates: list[str] = []
    with os.scandir(environments) as entries:
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            site_packages = os.path.join(entry.path, "Lib", "site-packages")
            if (
                os.path.isdir(site_packages)
                and not os.path.islink(site_packages)
                and not os.path.isjunction(site_packages)
            ):
                candidates.append(site_packages)
    if len(candidates) != 1:
        raise RuntimeError("Vadgr CUA must contain exactly one private package environment")
    site.addsitedir(candidates[0])


def main() -> None:
    _add_private_site_packages()
    module = "computer_use.mcp_server"
    arguments = sys.argv[1:]
    if arguments and arguments[0].startswith("computer_use."):
        module = arguments.pop(0)
    sys.argv = [module, *arguments]
    if os.environ.get("VADGR_CUA_PAYLOAD_PROBE") == "1":
        imported = __import__(module, fromlist=["main"])
        imported._start_browser_tier = lambda: None
        raise SystemExit(imported.main(arguments))
    runpy.run_module(module, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
