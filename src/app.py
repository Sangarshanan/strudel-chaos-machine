"""Entrypoint for strudel-chaos-machine."""

from __future__ import annotations

import argparse
import os


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default="https://strudel.cc",
                   help="Strudel URL to open (default: https://strudel.cc). "
                        "Also configurable via STRUDEL_URL env var.")
    p.add_argument("--headless", action="store_true",
                   help="Run Chromium headless (default: headed).")
    p.add_argument("--seed", type=int, default=None,
                   help="Optional RNG seed for reproducible chaos.")
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()

    os.environ.setdefault("STRUDEL_URL", args.url)
    if args.headless:
        os.environ["STRUDEL_HEADLESS"] = "1"
    if args.seed is not None:
        os.environ["STRUDEL_SEED"] = str(args.seed)

    from .mcp_server import run_server
    run_server()


if __name__ == "__main__":
    main()
