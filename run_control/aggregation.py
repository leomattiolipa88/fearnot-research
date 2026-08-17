"""Deterministic status aggregation.

Rules (encoded explicitly, never inferred by an LLM):

  SYSTEM RED  ← any CONTROL stage RED
              ← any PUBLICATION stage RED
              ← at least one DESK stage exists and *every* DESK stage is RED
                (no valid research surface left)
              ← there are no non-SKIPPED stages at all
  SYSTEM YELLOW ← any YELLOW without a system-critical RED
                 ← at least one DESK stage RED while another DESK stage is
                   GREEN or YELLOW (independent-desk failure)
                 ← any SUPPORT stage RED without RED elsewhere critical
  SYSTEM GREEN ← every stage is GREEN or legitimately SKIPPED
"""

from __future__ import annotations

from collections.abc import Iterable

from run_control.models import AggregateStatus, StageResult, StageStatus, StageType


def aggregate_status(results: Iterable[StageResult]) -> AggregateStatus:
    results = list(results)

    # Every ever-known stage still has a terminal status; if the entire list
    # is empty (or fully SKIPPED with no work at all), that is itself a
    # run-control failure — a run that produced nothing cannot be GREEN.
    if not results:
        return AggregateStatus.RED
    if all(r.status is StageStatus.SKIPPED for r in results):
        return AggregateStatus.RED

    def any_red(stage_type: StageType) -> bool:
        return any(
            r.stage_type is stage_type and r.status is StageStatus.RED for r in results
        )

    if any_red(StageType.CONTROL):
        return AggregateStatus.RED
    if any_red(StageType.PUBLICATION):
        return AggregateStatus.RED

    desk_results = [r for r in results if r.stage_type is StageType.DESK]
    if desk_results:
        desk_non_red = [r for r in desk_results if r.status is not StageStatus.RED]
        desk_alive = [
            r
            for r in desk_non_red
            if r.status in (StageStatus.GREEN, StageStatus.YELLOW)
        ]
        # Every desk RED and no desk left alive → no valid research produced.
        if not desk_alive and any(r.status is StageStatus.RED for r in desk_results):
            return AggregateStatus.RED

    has_red = any(r.status is StageStatus.RED for r in results)
    has_yellow = any(r.status is StageStatus.YELLOW for r in results)

    if has_red or has_yellow:
        return AggregateStatus.YELLOW

    # Everything is GREEN or SKIPPED and no critical failure survived.
    return AggregateStatus.GREEN
