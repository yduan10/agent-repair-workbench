"""Explicit local metadata administration; read operations do not initialize state."""

import argparse
import json

import anyio

from agent_workbench.run_store.execution import reconcile_runs
from agent_workbench.run_store.location import state_directory
from agent_workbench.run_store.models import StoreError
from agent_workbench.run_store.store import RunStore


def configure(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="runs_command", required=True)
    commands.add_parser("init", help="initialize or migrate the local run database")
    commands.add_parser("list", help="list the most recent local runs")
    for name in ("show", "report"):
        command = commands.add_parser(name)
        command.add_argument("run_id")
    commands.add_parser("reconcile", help="inspect expired execution leases without replaying work")
    prune = commands.add_parser("prune", help="preview eligible metadata deletion")
    prune.add_argument("--days", type=int, default=30)
    prune.add_argument("--apply", action="store_true")


def main(args: argparse.Namespace) -> int:
    store = RunStore(state_directory())
    try:
        if args.runs_command == "init":
            store.initialize()
            result: object = {"status": "ready"}
        elif args.runs_command == "list":
            result = {"runs": [run.model_dump(mode="json") for run in store.list_runs()]}
        elif args.runs_command == "show":
            result = store.detail(args.run_id).model_dump(mode="json")
        elif args.runs_command == "report":
            result = store.report(args.run_id).model_dump(mode="json")
        elif args.runs_command == "reconcile":
            result = {
                "runs": [run.model_dump(mode="json") for run in anyio.run(reconcile_runs, store)]
            }
        else:
            result = {"apply": args.apply, "run_ids": store.prune(days=args.days, apply=args.apply)}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0
    except StoreError as error:
        print(json.dumps({"error": error.code}))
        return 2
    finally:
        store.close()
