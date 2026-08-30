"""Start the pinned cua module from vadgr's isolated private interpreter."""

from __future__ import annotations

import runpy
import os
import sys


def main() -> None:
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
