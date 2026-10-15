"""Explicit local recovery; no model configuration, secret or arbitrary argv input."""

import argparse
import asyncio

from agent_workbench.mcp_config import ROOT
from agent_workbench.run_store.location import state_directory

from .inventory import RecoveryInventory
from .service import RecoveryService


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--task-id", required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Stop and remove precisely identified orphan containers, then reconcile unknown state. "
            "Without this flag inspect only; live or paused owners are always refused."
        ),
    )


def main(args: argparse.Namespace) -> int:
    store = None
    try:
        store = RecoveryInventory(state_directory())
        result = asyncio.run(RecoveryService(store, ROOT).recover(args.task_id, apply=args.apply))
        print(result.model_dump_json())
        return result.exit_code()
    except KeyboardInterrupt:
        print('{"error":"RECOVERY_INTERRUPTED"}')
    except Exception:
        print('{"error":"RECOVERY_UNAVAILABLE"}')
    finally:
        if store is not None:
            store.close()
    return 2
