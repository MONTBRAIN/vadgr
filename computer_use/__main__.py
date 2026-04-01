"""CLI entry point for autonomous mode.

Usage:
    python -m computer_use "Open Chrome and search for Vadgr"
    python -m computer_use --provider anthropic "Open Notepad"
    python -m computer_use --config custom.yaml "Click the Start menu"
    python -m computer_use --info  # Show platform info
"""

import argparse
import logging
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Computer Use Engine -- autonomous desktop control."
    )
    parser.add_argument(
        "task",
        nargs="?",
        help="Natural-language task description.",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="LLM provider (anthropic, openai).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=50,
        help="Maximum steps before stopping.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip action verification.",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Show platform info and exit.",
    )
    parser.add_argument(
        "--screenshot",
        type=str,
        default=None,
        metavar="PATH",
        help="Take a screenshot and save to PATH.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    from computer_use.core.engine import ComputerUseEngine

    # Info mode
    if args.info:
        engine = ComputerUseEngine(config_path=args.config)
        info = engine.get_platform_info()
        print(f"Platform: {info['platform']}")
        print(f"Backend available: {info['backend_available']}")
        print(f"Accessibility API: {info['accessibility']['api_name']}")
        print(f"Accessibility available: {info['accessibility']['available']}")
        if info["accessibility"].get("notes"):
            print(f"Notes: {info['accessibility']['notes']}")
        screen_w, screen_h = engine.get_screen_size()
        print(f"Screen size: {screen_w}x{screen_h}")
        return

    # Screenshot mode
    if args.screenshot:
        engine = ComputerUseEngine(config_path=args.config)
        screen = engine.screenshot()
        with open(args.screenshot, "wb") as f:
            f.write(screen.image_bytes)
        print(
            f"Screenshot saved to {args.screenshot} "
            f"({screen.width}x{screen.height})"
        )
        return

    # Task mode (autonomous)
    if not args.task:
        parser.error("A task description is required (or use --info / --screenshot)")

    provider = args.provider or "anthropic"
    engine = ComputerUseEngine(
        config_path=args.config,
        provider=provider,
    )

    print(f"Platform: {engine.get_platform().value}")
    print(f"Provider: {provider}")
    print(f"Task: {args.task}")
    print(f"Max steps: {args.max_steps}")
    print("---")

    results = engine.run_task(
        task=args.task,
        max_steps=args.max_steps,
        verify=not args.no_verify,
    )

    print(f"\nCompleted {len(results)} steps.")
    for i, r in enumerate(results, 1):
        status = "OK" if r.success else "FAILED"
        action = r.action_taken.action_type.value
        reason = r.reasoning[:80] if r.reasoning else ""
        print(f"  Step {i}: [{status}] {action} -- {reason}")
        if r.error:
            print(f"          Error: {r.error}")

    success_count = sum(1 for r in results if r.success)
    print(f"\n{success_count}/{len(results)} steps succeeded.")
    sys.exit(0 if all(r.success for r in results) else 1)


if __name__ == "__main__":
    main()
