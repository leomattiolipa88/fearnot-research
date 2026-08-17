"""Operator-facing CLI adapter for the M1 controlled daily run.

Purpose:
  Provide an exit-code contract so a naive operator running the wrapper
  from the terminal cannot mistake a SYSTEM RED run for a successful one.

Exit-code contract:
  * 0 — aggregate SYSTEM GREEN or SYSTEM YELLOW (run persisted; may have
        known incompleteness or an independent-desk failure)
  * 1 — aggregate SYSTEM RED (critical control/publication failure, or
        every desk failed, or an ordinary child failure that cascaded)
  * 2 — the manifest could not be produced at all (finalization or IO
        failure) — nothing was persisted to disk

Manifest persistence happens BEFORE the exit code is derived. A RED run
still produces a complete, machine-readable manifest for later review.

This module is NOT an M10 canonical runner. It is NOT wired into GitHub
Actions. It changes no research commands.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from run_control.daily_wrapper import DailyRunConfig, build_default_config, run_daily
from run_control.manifest import manifest_path
from run_control.models import AggregateStatus, RunRecord, StageStatus

EXIT_OK = 0
EXIT_SYSTEM_RED = 1
EXIT_MANIFEST_FAILURE = 2


def has_execution_failure(run: RunRecord) -> bool:
    """True iff any stage_result is RED.

    Provenance note: in the daily wrapper's world, every RED StageResult
    originates from a genuine execution failure — either a child process
    exited nonzero (ProcessFailed) or the callable raised inside
    ``execute_stage``. There is no "semantic RED" that the wrapper itself
    can produce. Callers that build RunRecords through other paths and
    plant a RED for non-execution reasons should not rely on this helper.
    """
    return any(r.status is StageStatus.RED for r in run.stage_results)


def derive_exit_code(run: RunRecord) -> int:
    """Operator exit code for a controlled wrapper run.

    Nonzero if the run encountered a genuine execution failure:
      * aggregate_status is SYSTEM RED (control-critical failure), OR
      * any StageResult is RED (a subprocess exited nonzero, raised, or
        violated the runner contract).

    The second clause is required because the audit-validated aggregation
    intentionally maps a lone SUPPORT-stage RED to SYSTEM YELLOW — that
    is correct for an observability status, but the operator must still
    see a nonzero exit when a child process actually failed. This split
    keeps aggregation semantics untouched while surfacing execution
    provenance at the CLI boundary (spec preferred design).
    """
    if run.aggregate_status is AggregateStatus.RED:
        return EXIT_SYSTEM_RED
    if has_execution_failure(run):
        return EXIT_SYSTEM_RED
    return EXIT_OK


def cli_run(config: DailyRunConfig) -> tuple[int, RunRecord | None]:
    """Run the daily wrapper and derive an operator exit code.

    Returns ``(exit_code, run_record_or_None)``. The manifest is always
    written before this function returns unless the wrapper itself
    could not finalize a run — in which case ``exit_code == 2`` and the
    returned record is ``None``.
    """
    try:
        run = run_daily(config)
    except BaseException:  # noqa: BLE001 — CLI must not raise on failure
        return EXIT_MANIFEST_FAILURE, None
    return derive_exit_code(run), run


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m run_control.cli",
        description=(
            "Opt-in M1 controlled run of the Fear Not daily pipeline. "
            "Runs existing stages unchanged, writes an auditable manifest, "
            "and exits nonzero on SYSTEM RED. Does NOT push to GitHub."
        ),
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root that the child processes should run against.",
    )
    p.add_argument(
        "--logs-dir",
        type=Path,
        default=None,
        help="Directory where the manifest is written (default: <repo-root>/logs).",
    )
    p.add_argument(
        "--trigger",
        default="manual",
        help="Free-form trigger label recorded in the manifest.",
    )
    monday = p.add_mutually_exclusive_group()
    monday.add_argument(
        "--monday",
        action="store_true",
        help="Force Monday semantics (synthesizer runs).",
    )
    monday.add_argument(
        "--not-monday",
        action="store_true",
        help="Force non-Monday semantics (synthesizer SKIPPED).",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    is_monday: bool | None = None
    if args.monday:
        is_monday = True
    elif args.not_monday:
        is_monday = False
    config = build_default_config(
        repo_root=args.repo_root,
        is_monday=is_monday,
        trigger=args.trigger,
        logs_dir=args.logs_dir,
    )
    exit_code, run = cli_run(config)
    if run is None:
        print("m1-cli: manifest could not be produced", file=sys.stderr)
    else:
        path = manifest_path(run.run_id, config.logs_dir)
        agg = run.aggregate_status.value if run.aggregate_status else "UNKNOWN"
        print(f"run_id={run.run_id}")
        print(f"aggregate_status={agg}")
        print(f"manifest={path}")
        if exit_code == EXIT_SYSTEM_RED:
            reds = [r.stage_name for r in run.stage_results if r.status.value == "RED"]
            print(f"failed_stages={reds}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
