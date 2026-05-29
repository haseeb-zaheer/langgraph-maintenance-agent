"""Command line interface for the LangGraph maintenance agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from langgraph_maintenance_agent import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="langgraph-maintenance",
        description="Run and manage the LangGraph routine maintenance agent.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command")

    validate_config = subparsers.add_parser(
        "validate-config",
        help="Validate a repository allowlist config file.",
    )
    validate_config.add_argument("config", type=Path)

    subparsers.add_parser("version", help="Print the package version.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    if args.command == "validate-config":
        # Real validation is added in the config schema checkpoint.
        if not args.config.exists():
            parser.error(f"config file does not exist: {args.config}")
        print(f"Config file exists: {args.config}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
