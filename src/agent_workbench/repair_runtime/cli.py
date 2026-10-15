"""Explicit new-task repair command for two fixed audited public fixtures only."""

import argparse
import asyncio
import json
from uuid import uuid4

from pydantic import ValidationError

from agent_workbench.candidate_execution.docker import verified_image
from agent_workbench.candidates.contracts import CandidateError
from agent_workbench.candidates.snapshots import SnapshotStore
from agent_workbench.controlled_tools.resources import load_repair_case
from agent_workbench.controlled_tools.responses import ResourceError
from agent_workbench.mcp_config import ROOT
from agent_workbench.model_gateway.gateway import Config, GatewayError
from agent_workbench.model_gateway.repair import RepairDeepSeekAdapter
from agent_workbench.orchestration.contracts import Budget
from agent_workbench.repair_cases.profiles import get_profile
from agent_workbench.repair_store.reproductions import ReproductionStore
from agent_workbench.run_store.location import state_directory
from agent_workbench.run_store.models import StoreError
from agent_workbench.run_store.store import RunStore

from .controller import RepairController, RepairResult


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--case", choices=("output_mismatch", "counter_offset"), default="output_mismatch"
    )
    parser.add_argument("--mode", choices=("single_role", "three_role"), default="three_role")
    parser.add_argument("--total-tokens", type=int, default=2_000_000)
    parser.add_argument("--output-tokens", type=int, default=8192)
    parser.add_argument("--model-calls", type=int, default=12)
    parser.add_argument("--tool-calls", type=int, default=20)
    parser.add_argument("--candidates", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=600)


def main(args: argparse.Namespace) -> int:
    store: ReproductionStore | None = None
    result: RepairResult | None = None
    try:
        profile = get_profile(args.case)
        budget = Budget(
            total_tokens=args.total_tokens,
            output_tokens=args.output_tokens,
            model_calls=args.model_calls,
            tool_calls=args.tool_calls,
            candidates=args.candidates,
            timeout_seconds=args.timeout,
        )
        if budget.output_tokens > 8192:
            raise ValueError("repair_output_limit")
        adapter = RepairDeepSeekAdapter(Config.from_env())
        directory = state_directory()
        # Public read enforces the current schema without creating/migrating state.
        preflight = RunStore(directory)
        try:
            if not preflight.path.exists():
                raise StoreError("not_found")
            preflight.list_runs(limit=1)
        finally:
            preflight.close()
        try:
            verified_image(ROOT)
        except (OSError, ValueError):
            print('{"error":"IMAGE_NOT_PREPARED"}')
            return 2
        task_id = str(uuid4())
        registry = load_repair_case(profile.case_id, task_id=task_id, budget=budget)
        snapshots = SnapshotStore(directory / "repair-snapshots")
        baseline = snapshots.create_baseline(str(uuid4()), case_id=profile.case_id)
        store = ReproductionStore(directory)
        result = asyncio.run(
            RepairController(
                store=store,
                snapshots=snapshots,
                baseline=baseline,
                registry=registry,
                adapter=adapter,
                mode=args.mode,
                image_root=ROOT,
            ).run()
        )
        task = result.cursor.task
        candidates = store.candidates(task.task_id)
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "task": task.model_dump(mode="json"),
                    "sha256": result.cursor.task_sha256,
                    "candidate_ids": [item.candidate_id for item in candidates],
                    "requires_reconcile": result.requires_reconcile,
                    "cancelled": result.cancelled,
                },
                ensure_ascii=True,
                separators=(",", ":"),
            )
        )
        return (
            0
            if task.outcome == "candidate_verified"
            and not result.requires_reconcile
            and not result.cancelled
            else 2
        )
    except GatewayError:
        print('{"error":"MODEL_CONFIGURATION_INVALID"}')
    except StoreError as error:
        code = {
            "not_found": "STATE_NOT_INITIALIZED",
            "schema_incompatible": "STATE_SCHEMA_INCOMPATIBLE",
        }.get(error.code, "STATE_UNAVAILABLE")
        payload: dict[str, object] = {"error": code}
        if result is not None:
            # Preserve a recovery handle if reading the final candidates fails.
            payload.update(
                task_id=result.cursor.task.task_id,
                sha256=result.cursor.task_sha256,
                requires_reconcile=True,
            )
        print(json.dumps(payload))
    except (CandidateError, ResourceError):
        print('{"error":"AUDITED_RESOURCE_UNAVAILABLE"}')
    except (ValidationError, ValueError, TypeError):
        print('{"error":"INVALID_CONFIGURATION"}')
    except KeyboardInterrupt:
        print('{"error":"CANCELLED"}')
    except Exception:
        print('{"error":"REPAIR_UNAVAILABLE"}')
    finally:
        if store is not None:
            store.close()
    return 2
