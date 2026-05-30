"""Command line interface for the LangGraph maintenance agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from langgraph_maintenance_agent import __version__
from langgraph_maintenance_agent.config import ConfigError, load_config


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
        try:
            config = load_config(args.config)
        except ConfigError as exc:
            parser.exit(status=1, message=f"Config validation failed: {exc}\n")
        enabled_count = sum(1 for repo in config.repos if repo.enabled)
        print(
            f"Config valid: {args.config} "
            f"({enabled_count}/{len(config.repos)} repos enabled)"
        )
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
