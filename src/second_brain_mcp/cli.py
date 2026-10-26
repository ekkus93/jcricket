"""Command-line entry point for the Second Brain MCP server."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .store import ConversationStore


def main() -> None:
    parser = argparse.ArgumentParser(prog="second-brain")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument(
        "command",
        choices=("serve", "check-config", "conversations"),
    )
    parser.add_argument(
        "action", nargs="?", choices=("list", "show", "delete", "purge")
    )
    parser.add_argument("conversation_id", nargs="?")
    parser.add_argument("--principal")
    parser.add_argument("--older-than", type=int)
    parser.add_argument("--yes", action="store_true", help="confirm bulk purge")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command == "check-config":
        config.credentials()
        print("Configuration is valid.")
        return
    if args.command == "conversations":
        _conversations(config.database_path, args)
        return
    from .server import run

    run(config)


def _conversations(database_path: Path, args: argparse.Namespace) -> None:
    if not args.action:
        raise SystemExit("conversations requires list, show, delete, or purge")
    store = ConversationStore(database_path)
    if args.action == "list":
        print(json.dumps(store.list(args.principal), indent=2))
    elif args.action == "show":
        if not args.conversation_id:
            raise SystemExit("show requires a conversation ID")
        conversation = store.list()
        if not any(row["id"] == args.conversation_id for row in conversation):
            raise SystemExit("conversation not found")
        print(
            json.dumps(
                [turn.__dict__ for turn in store.show(args.conversation_id)], indent=2
            )
        )
    elif args.action == "delete":
        if not args.conversation_id:
            raise SystemExit("delete requires a conversation ID")
        if not store.delete(args.conversation_id):
            raise SystemExit("conversation not found")
    else:
        if args.older_than is None or args.older_than < 1:
            raise SystemExit(
                "purge requires --older-than with a positive number of days"
            )
        if not args.yes:
            answer = input(
                f"Delete conversations older than {args.older_than} days? [y/N] "
            )
            if answer.strip().lower() != "y":
                print("Purge cancelled.")
                return
        print(f"Deleted {store.purge(args.older_than)} conversations.")
