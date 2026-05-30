"""Command line interface for the LangGraph maintenance agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from langgraph_maintenance_agent import __version__
from langgraph_maintenance_agent.config import ConfigError, load_config
from langgraph_maintenance_agent.graph import run_workflow
from langgraph_maintenance_agent.llm.openrouter import OpenRouterConfigError
from langgraph_maintenance_agent.reporting.discord import (
    DiscordDeliveryError,
    send_discord_content,
)
from langgraph_maintenance_agent.reporting.markdown import compact_discord_summary


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
    run.add_argument("--max-concurrency", type=int, default=4)
    delivery = run.add_mutually_exclusive_group()
    delivery.add_argument("--send-discord", action="store_true")
    delivery.add_argument("--no-discord", action="store_true")
    run.add_argument("--summary-only", action="store_true")

    send = subparsers.add_parser("send", help="Send a rendered report to Discord.")
    send.add_argument("report_path", type=Path)
    send.add_argument("--summary-only", action="store_true")

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
            send_discord: bool | None = None
            if args.send_discord:
                send_discord = True
            elif args.no_discord:
                send_discord = False
            state = run_workflow(
                config_path=args.config,
                output_dir=args.output_dir,
                dry_run=args.dry_run,
                use_llm=args.llm,
                provider=args.provider,
                max_tool_calls=args.max_tool_calls,
                max_agent_iterations=args.max_agent_iterations,
                max_concurrency=args.max_concurrency,
                send_discord=send_discord,
                summary_only=args.summary_only,
            )
        except (ConfigError, OpenRouterConfigError, RuntimeError) as exc:
            parser.exit(status=1, message=f"Workflow failed: {exc}\n")
        report_path = state.get("report_path") or "not written"
        discord_status = state.get("discord_status")
        discord_message = ""
        if discord_status and discord_status.attempted:
            if discord_status.success:
                discord_message = f", Discord {discord_status.message}"
            else:
                discord_message = f", Discord failed: {discord_status.message}"
        print(
            "Workflow complete: "
            f"{len(state.get('repo_results', []))} repo(s), "
            f"{len(state.get('findings', []))} finding(s), "
            f"report {report_path}"
            f"{discord_message}"
        )
        return 0

    if args.command == "send":
        if not args.report_path.exists() or not args.report_path.is_file():
            parser.exit(
                status=1,
                message=f"Report file not found: {args.report_path}\n",
            )
        report = args.report_path.read_text(encoding="utf-8")
        content = (
            compact_discord_summary(report, str(args.report_path))
            if args.summary_only
            else report
        )
        try:
            result = send_discord_content(content)
        except DiscordDeliveryError as exc:
            parser.exit(status=1, message=f"Discord delivery failed: {exc}\n")
        print(f"Discord delivery complete: sent {result.messages_sent} message(s)")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
