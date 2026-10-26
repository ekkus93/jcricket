"""Command-line entry point for the Second Brain MCP server and admin tools."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from .config import AppConfig, load_config
from .errors import SecondBrainError
from .ollama import verify_context_windows
from .store import ConversationStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="second-brain")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="run the MCP server")
    commands.add_parser("check-config", help="validate configuration and credentials")

    conversations = commands.add_parser("conversations")
    actions = conversations.add_subparsers(dest="action", required=True)
    listing = actions.add_parser("list")
    listing.add_argument("--principal")
    for action_name in ("show", "get-any", "delete"):
        action = actions.add_parser(action_name)
        action.add_argument("conversation_id")
        if action_name == "delete":
            action.add_argument("--yes", action="store_true")
    purge = actions.add_parser("purge")
    purge.add_argument("--older-than", type=int)
    purge.add_argument("--yes", action="store_true")
    export = actions.add_parser("export")
    export.add_argument("conversation_id", nargs="?")
    export.add_argument("--principal")
    export.add_argument("--output", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        config = load_config(args.config)
        if args.command in {"check-config", "serve"}:
            config.credentials()
    except ValueError as exc:
        print(f"second-brain: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    if args.command in {"check-config", "serve"}:
        _verify_context_windows(config, required=args.command == "check-config")
    if args.command == "check-config":
        print("Configuration is valid.")
    elif args.command == "conversations":
        _conversations(config, args)
    else:
        from .server import run

        run(config)


def _verify_context_windows(config: AppConfig, *, required: bool) -> None:
    """Fail on budgets larger than a model's real window; warn when unverifiable."""
    try:
        report = asyncio.run(verify_context_windows(config))
    except SecondBrainError as exc:
        message = f"could not verify model context windows: {exc}"
        if required:
            print(f"second-brain: {message}", file=sys.stderr)
            raise SystemExit(1) from None
        print(f"second-brain: warning: {message}", file=sys.stderr)
        return
    for warning in report.warnings:
        print(f"second-brain: warning: {warning}", file=sys.stderr)
    for error in report.errors:
        print(f"second-brain: {error}", file=sys.stderr)
    if report.errors:
        raise SystemExit(1)


def _conversations(config: Any, args: argparse.Namespace) -> None:
    database_path = getattr(config, "database_path", config)
    retention_days = getattr(config, "retention_days", None)
    store = ConversationStore(database_path)
    if args.action == "list":
        print(json.dumps(store.list(args.principal), indent=2))
    elif args.action == "get-any":
        metadata = store.get_any(args.conversation_id)
        if metadata is None:
            raise SystemExit("conversation not found")
        print(json.dumps(metadata, indent=2))
    elif args.action == "show":
        metadata = store.get_any(args.conversation_id)
        if metadata is None:
            raise SystemExit("conversation not found")
        print(json.dumps(_export_conversation(store, metadata), indent=2))
    elif args.action == "delete":
        if not args.yes and not _confirm(
            f"Delete conversation {args.conversation_id}? [y/N] "
        ):
            raise SystemExit("Cancelled.")
        if not store.delete(args.conversation_id):
            raise SystemExit("conversation not found")
    elif args.action == "purge":
        age = args.older_than if args.older_than is not None else retention_days
        if age is None or age < 1:
            raise SystemExit("purge requires --older-than or configured retention_days")
        if not args.yes and not _confirm(
            f"Delete conversations older than {age} days? [y/N] "
        ):
            raise SystemExit("Cancelled.")
        print(f"Deleted {store.purge(age)} conversations.")
    elif args.action == "export":
        if args.conversation_id:
            metadata = store.get_any(args.conversation_id)
            records = (
                [] if metadata is None else [_export_conversation(store, metadata)]
            )
        else:
            records = [
                _export_conversation(store, item) for item in store.list(args.principal)
            ]
        if args.conversation_id and not records:
            raise SystemExit("conversation not found")
        payload = json.dumps(records, indent=2) + "\n"
        if args.output is None:
            print(payload, end="")
        else:
            _create_private_export(args.output, payload)


def _export_conversation(
    store: ConversationStore, metadata: dict[str, Any]
) -> dict[str, Any]:
    return {
        "conversation": metadata,
        "turns": [turn.__dict__ for turn in store.show(metadata["id"])],
    }


def _create_private_export(path: Path, contents: str) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(contents)
    path.chmod(0o600)


def _confirm(prompt: str) -> bool:
    if not sys.stdin.isatty():
        return False
    try:
        answer = input(prompt)
    except EOFError:
        return False
    return answer.strip().lower() == "y"


if __name__ == "__main__":
    main()
