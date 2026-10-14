"""Explicit local CLI; no credential flags and no model calls from web requests."""

import argparse
import asyncio
import json
from uuid import uuid4

from pydantic import ValidationError

from agent_workbench.analysis_store.store import AnalysisStore
from agent_workbench.controlled_tools.resources import load_case
from agent_workbench.controlled_tools.responses import ResourceError
from agent_workbench.model_gateway.gateway import Config, DeepSeekAdapter, GatewayError
from agent_workbench.orchestration.contracts import Budget
from agent_workbench.orchestration.runtime import AnalysisRuntime
from agent_workbench.run_store.location import state_directory
from agent_workbench.run_store.models import StoreError


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--case", choices=("output_mismatch", "passing"), required=True)
    parser.add_argument(
        "--intent", choices=("check_only", "diagnose", "propose_repair"), default="diagnose"
    )
    parser.add_argument("--total-tokens", type=int, default=2_000_000)
    parser.add_argument("--output-tokens", type=int, default=8192)
    parser.add_argument("--model-calls", type=int, default=12)
    parser.add_argument("--tool-calls", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=600)


def configure_history(parser: argparse.ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="analysis_command", required=True)
    commands.add_parser("list")
    for command in ("show", "reconcile"):
        commands.add_parser(command).add_argument("task_id")


def main(args: argparse.Namespace) -> int:
    store = AnalysisStore(state_directory())
    try:
        if args.command == "analyses":
            if args.analysis_command == "list":
                print(
                    json.dumps(
                        {
                            "analyses": [
                                {
                                    "summary": item.summary.model_dump(mode="json"),
                                    "sha256": item.sha256,
                                }
                                for item in store.list()
                            ]
                        }
                    )
                )
                return 0
            result = store.get(args.task_id)
            if args.analysis_command == "reconcile":
                result = store.reconcile(
                    args.task_id,
                    expected_revision=result.summary.summary_revision,
                    expected_sha256=result.sha256,
                )
        else:
            budget = Budget(
                total_tokens=args.total_tokens,
                output_tokens=args.output_tokens,
                model_calls=args.model_calls,
                tool_calls=args.tool_calls,
                timeout_seconds=args.timeout,
            )
            adapter = None if args.intent == "check_only" else DeepSeekAdapter(Config.from_env())
            registry = load_case(args.case, task_id=str(uuid4()), intent=args.intent, budget=budget)
            result = asyncio.run(AnalysisRuntime(registry, store, adapter).run())
        print(
            json.dumps(
                {"summary": result.summary.model_dump(mode="json"), "sha256": result.sha256},
                ensure_ascii=True,
                separators=(",", ":"),
            )
        )
        return (
            0
            if result.summary.state.outcome
            in {"check_complete", "diagnosis_complete", "proposal_only"}
            else 2
        )
    except (GatewayError, ResourceError, StoreError) as exc:
        print(json.dumps({"error": getattr(exc, "code", str(exc))}))
        return 2
    except (ValidationError, ValueError):
        print('{"error":"INVALID_CONFIGURATION"}')
        return 2
    except KeyboardInterrupt:
        print('{"error":"CANCELLED"}')
        return 2
    finally:
        store.close()
