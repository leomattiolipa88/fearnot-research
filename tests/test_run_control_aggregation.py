"""Deterministic status aggregation tests."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from run_control import (
    AggregateStatus,
    StageResult,
    StageStatus,
    StageType,
    aggregate_status,
    utc_now,
)


def _stage(
    name: str,
    stype: StageType,
    status: StageStatus,
    skip_reason: str | None = None,
) -> StageResult:
    now = utc_now()
    kwargs = {}
    if status is StageStatus.RED:
        kwargs["safe_error_summary"] = f"{name}: simulated failure for test"
    if skip_reason is not None:
        kwargs["skip_reason"] = skip_reason
    return StageResult(
        stage_name=name,
        stage_type=stype,
        started_at=now,
        ended_at=now + timedelta(milliseconds=1),
        status=status,
        **kwargs,
    )


class TestAggregation:
    def test_all_green_is_system_green(self):
        results = [
            _stage("control", StageType.CONTROL, StageStatus.GREEN),
            _stage("macro", StageType.DESK, StageStatus.GREEN),
            _stage("web", StageType.PUBLICATION, StageStatus.GREEN),
        ]
        assert aggregate_status(results) is AggregateStatus.GREEN

    def test_green_plus_yellow_is_system_yellow(self):
        results = [
            _stage("control", StageType.CONTROL, StageStatus.GREEN),
            _stage("macro", StageType.DESK, StageStatus.GREEN),
            _stage("banking", StageType.DESK, StageStatus.YELLOW),
        ]
        assert aggregate_status(results) is AggregateStatus.YELLOW

    def test_green_plus_legitimate_skipped_is_green(self):
        results = [
            _stage("control", StageType.CONTROL, StageStatus.GREEN),
            _stage("macro", StageType.DESK, StageStatus.GREEN),
            _stage(
                "synthesizer",
                StageType.DESK,
                StageStatus.SKIPPED,
                skip_reason="Monday-only stage",
            ),
        ]
        assert aggregate_status(results) is AggregateStatus.GREEN

    def test_one_desk_red_other_desks_green_is_yellow(self):
        results = [
            _stage("control", StageType.CONTROL, StageStatus.GREEN),
            _stage("macro", StageType.DESK, StageStatus.RED),
            _stage("technical", StageType.DESK, StageStatus.GREEN),
            _stage("energy", StageType.DESK, StageStatus.GREEN),
        ]
        assert aggregate_status(results) is AggregateStatus.YELLOW

    def test_critical_control_red_is_system_red(self):
        results = [
            _stage("control", StageType.CONTROL, StageStatus.RED),
            _stage("macro", StageType.DESK, StageStatus.GREEN),
        ]
        assert aggregate_status(results) is AggregateStatus.RED

    def test_critical_publication_red_is_system_red(self):
        results = [
            _stage("control", StageType.CONTROL, StageStatus.GREEN),
            _stage("macro", StageType.DESK, StageStatus.GREEN),
            _stage("web", StageType.PUBLICATION, StageStatus.RED),
        ]
        assert aggregate_status(results) is AggregateStatus.RED

    def test_multiple_desk_red_with_surviving_desk_is_yellow(self):
        results = [
            _stage("control", StageType.CONTROL, StageStatus.GREEN),
            _stage("macro", StageType.DESK, StageStatus.RED),
            _stage("technical", StageType.DESK, StageStatus.RED),
            _stage("energy", StageType.DESK, StageStatus.GREEN),
        ]
        assert aggregate_status(results) is AggregateStatus.YELLOW

    def test_every_desk_red_and_no_survivor_is_system_red(self):
        results = [
            _stage("control", StageType.CONTROL, StageStatus.GREEN),
            _stage("macro", StageType.DESK, StageStatus.RED),
            _stage("technical", StageType.DESK, StageStatus.RED),
            _stage("energy", StageType.DESK, StageStatus.RED),
        ]
        assert aggregate_status(results) is AggregateStatus.RED

    def test_skipped_cannot_hide_red(self):
        """A RED stage in the same run cannot be masked by SKIPPED siblings."""
        results = [
            _stage("control", StageType.CONTROL, StageStatus.GREEN),
            _stage("macro", StageType.DESK, StageStatus.RED),
            _stage(
                "synthesizer",
                StageType.DESK,
                StageStatus.SKIPPED,
                skip_reason="not Monday",
            ),
        ]
        # RED is not consumed by SKIPPED — surviving desk = synthesizer? No,
        # synthesizer is SKIPPED, so no *alive* desk remains and it must be RED.
        assert aggregate_status(results) is AggregateStatus.RED

    def test_empty_result_list_is_red(self):
        assert aggregate_status([]) is AggregateStatus.RED

    def test_all_skipped_is_red(self):
        results = [
            _stage(
                "control",
                StageType.CONTROL,
                StageStatus.SKIPPED,
                skip_reason="not implemented",
            ),
        ]
        assert aggregate_status(results) is AggregateStatus.RED

    def test_deterministic_across_input_order(self):
        base = [
            _stage("control", StageType.CONTROL, StageStatus.GREEN),
            _stage("macro", StageType.DESK, StageStatus.RED),
            _stage("technical", StageType.DESK, StageStatus.GREEN),
            _stage("web", StageType.PUBLICATION, StageStatus.YELLOW),
        ]
        assert aggregate_status(base) is aggregate_status(list(reversed(base)))
