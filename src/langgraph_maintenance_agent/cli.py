"""Command line interface for the LangGraph maintenance agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from langgraph_maintenance_agent import __version__
from langgraph_maintenance_agent.config import ConfigError, load_config
from langgraph_maintenance_agent.graph import run_workflow
from langgraph_maintenance_agent.llm.openrouter import OpenRouterConfigError


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

    run = subparsers.add_parser("run", help="Run the maintenance workflow.")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output-dir", type=Path)
    mode = run.add_mutually_exclusive_group()
    mode.add_argument(
        "--llm", action="store_true", help="Use OpenRouter-backed agents."
    )
    mode.add_argument(
        "--no-llm", action="store_true", help="Use deterministic fallback."
    )
    run.add_argument("--provider", default="openrouter")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--max-tool-calls", type=int, default=12)
    run.add_argument("--max-agent-iterations", type=int, default=6)

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

    if args.command == "run":
        try:
            state = run_workflow(
                config_path=args.config,
                output_dir=args.output_dir,
                dry_run=args.dry_run,
                use_llm=args.llm,
                provider=args.provider,
                max_tool_calls=args.max_tool_calls,
                max_agent_iterations=args.max_agent_iterations,
            )
        except (ConfigError, OpenRouterConfigError) as exc:
            parser.exit(status=1, message=f"Workflow failed: {exc}\n")
        report_path = state.get("report_path") or "not written"
        print(
            "Workflow complete: "
            f"{len(state.get('repo_results', []))} repo(s), "
            f"{len(state.get('findings', []))} finding(s), "
            f"report {report_path}"
        )
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
