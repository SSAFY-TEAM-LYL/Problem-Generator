"""``python -m ipe.sandbox`` — sandbox isolation self-test CLI.

Usage:
    python -m ipe.sandbox --tier auto
    python -m ipe.sandbox --tier docker
    python -m ipe.sandbox --tier sandboxexec
    python -m ipe.sandbox --tier rlimit

Exit code: 0=all pass, 1=some checks failed, 2=runner instantiation error.
"""

from __future__ import annotations

import argparse
import json
import sys

from ipe.sandbox.selector import pick_runner


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="python -m ipe.sandbox",
        description="IPE sandbox isolation self-test",
    )
    ap.add_argument(
        "--tier",
        default="auto",
        choices=["auto", "docker", "sandboxexec", "rlimit"],
        help="sandbox tier 선택 (default: auto)",
    )
    args = ap.parse_args()

    try:
        runner = pick_runner(args.tier, verbose=True)
    except RuntimeError as e:
        print(f"Failed to instantiate runner: {e}", file=sys.stderr)
        return 2

    print(f"Using runner: {runner.tier}")
    print("Running isolation self-test (this may take a few seconds)...")
    results = runner.isolation_self_test()
    print(json.dumps(results, indent=2, ensure_ascii=False))

    if all(results.values()):
        print("✅ all isolation checks passed")
        return 0
    failed = [k for k, v in results.items() if not v]
    print(f"⚠️  failed checks: {failed}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
