from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from .companion import PersonalCompanion
from .interpreter import Interpreter
from .vault import VaultManager


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Personal AI Companion")
    parser.add_argument("--vault", default="vault", help="Path to the vault directory")
    subparsers = parser.add_subparsers(dest="command")

    scaffold = subparsers.add_parser("scaffold", help="Create the vault scaffold")
    scaffold.set_defaults(action="scaffold")

    chat = subparsers.add_parser("chat", help="Start a simple chat loop")
    chat.set_defaults(action="chat")

    recall = subparsers.add_parser("recall", help="Search the vault for a query")
    recall.add_argument("query", help="Search query")
    recall.set_defaults(action="recall")

    serve = subparsers.add_parser("serve", help="Start the local API server")
    serve.add_argument("--vault", default="vault", help="Path to the vault directory")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(action="serve")

    return parser


def _simple_chat(vault_root: Path) -> None:
    manager = VaultManager(vault_root)
    companion = PersonalCompanion(vault_root=vault_root)
    print("Personal AI Companion shell. Type 'exit' to quit.")
    while True:
        user_input = input("You> ")
        if user_input.strip().lower() in {"exit", "quit"}:
            print("Goodbye.")
            return
        result = companion.process_turn(user_input)
        print(f"Interpreter mode: {result['interpretation']['mode_suggestion']}")
        print(f"Action: {result['action']}")
        print(f"Reply: {result['reply']}")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    vault_root = Path(args.vault)

    if getattr(args, "action", None) == "scaffold":
        manager = VaultManager(vault_root)
        manager.ensure_scaffold()
        print(f"Vault scaffold created at {vault_root}")
        return

    if getattr(args, "action", None) == "recall":
        manager = VaultManager(vault_root)
        for result in manager.search(args.query):
            print(f"- {result.file_path} :: {result.date or 'unknown'}")
        return

    if getattr(args, "action", None) == "chat":
        _simple_chat(vault_root)
        return

    if getattr(args, "action", None) == "serve":
        from .server import app

        uvicorn.run(app, host=args.host, port=args.port)
        return

    if args.command is None:
        _simple_chat(vault_root)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
