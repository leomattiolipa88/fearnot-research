"""Unit tests for M1 primitives: run_id, timestamps, StageResult, metadata."""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from run_control import (
    RunRecord,
    StageResult,
    StageStatus,
    StageType,
    generate_run_id,
    is_valid_run_id,
    utc_now,
)


# ── A. Run ID ─────────────────────────────────────────────────────────────────


class TestRunId:
    def test_format_matches_contract(self):
        rid = generate_run_id()
        assert is_valid_run_id(rid), rid
        assert rid.startswith("FN-")
        assert re.match(r"^FN-\d{8}T\d{6}Z-[0-9a-f]{8}$", rid)

    def test_generated_ids_are_unique(self):
        ids = {generate_run_id() for _ in range(2000)}
        assert len(ids) == 2000

    def test_ids_generated_same_second_still_unique(self):
        fixed = datetime(2026, 8, 16, 14, 1, 2, tzinfo=timezone.utc)
        ids = {generate_run_id(now=fixed) for _ in range(500)}
        assert len(ids) == 500

    def test_id_is_immutable_string(self):
        rid = generate_run_id()
        assert isinstance(rid, str)

    def test_ids_generated_from_utc_only(self):
        aware_utc = datetime(2026, 8, 16, 14, 1, 2, tzinfo=timezone.utc)
        aware_offset = aware_utc.astimezone(timezone(timedelta(hours=-3)))
        stamp_utc = generate_run_id(now=aware_utc).split("-")[1]
        stamp_off = generate_run_id(now=aware_offset).split("-")[1]
        assert stamp_utc == stamp_off

    def test_generator_rejects_naive_datetime(self):
        with pytest.raises(ValueError):
            generate_run_id(now=datetime(2026, 1, 1))

    def test_generator_rejects_non_datetime(self):
        with pytest.raises(TypeError):
            generate_run_id(now="2026-01-01")  # type: ignore[arg-type]

    def test_validator_rejects_bad_shapes(self):
        assert not is_valid_run_id("")
        assert not is_valid_run_id("FN-20260816-abcd")
        assert not is_valid_run_id("FN-20260816T140102Z-XYZ12345")
        assert not is_valid_run_id(None)  # type: ignore[arg-type]

    def test_validator_rejects_impossible_dates(self):
        # Right shape, impossible calendar date (Feb 32).
        assert not is_valid_run_id("FN-20260232T140102Z-abcdef01")
        # 24:00:00 is not a valid time-of-day for strptime.
        assert not is_valid_run_id("FN-20260816T240000Z-abcdef01")


# ── B. Timestamps ─────────────────────────────────────────────────────────────


class TestTimestamps:
    def test_utc_now_is_timezone_aware(self):
        t = utc_now()
        assert t.tzinfo is not None
        assert t.utcoffset() == timedelta(0)

    def test_stage_result_rejects_naive_started_at(self):
        with pytest.raises(ValueError):
            StageResult(
                stage_name="x",
                stage_type=StageType.CONTROL,
                started_at=datetime(2026, 1, 1),  # naive
                ended_at=utc_now(),
                status=StageStatus.GREEN,
            )

    def test_stage_result_rejects_naive_ended_at(self):
        with pytest.raises(ValueError):
            StageResult(
                stage_name="x",
                stage_type=StageType.CONTROL,
                started_at=utc_now(),
                ended_at=datetime(2026, 1, 1),  # naive
                status=StageStatus.GREEN,
            )

    def test_stage_result_rejects_missing_started_at(self):
        with pytest.raises(ValueError):
            StageResult(
                stage_name="x",
                stage_type=StageType.CONTROL,
                started_at=None,  # type: ignore[arg-type]
                ended_at=utc_now(),
                status=StageStatus.GREEN,
            )

    def test_stage_result_rejects_missing_ended_at(self):
        with pytest.raises(ValueError):
            StageResult(
                stage_name="x",
                stage_type=StageType.CONTROL,
                started_at=utc_now(),
                ended_at=None,  # type: ignore[arg-type]
                status=StageStatus.GREEN,
            )

    def test_stage_result_start_before_end(self):
        start = utc_now()
        end = start + timedelta(seconds=1)
        stage = StageResult(
            stage_name="x",
            stage_type=StageType.CONTROL,
            started_at=start,
            ended_at=end,
            status=StageStatus.GREEN,
        )
        assert stage.ended_at >= stage.started_at

    def test_stage_result_rejects_end_before_start(self):
        start = utc_now()
        with pytest.raises(ValueError):
            StageResult(
                stage_name="x",
                stage_type=StageType.CONTROL,
                started_at=start,
                ended_at=start - timedelta(seconds=1),
                status=StageStatus.GREEN,
            )


# ── C. StageResult contract & invariants ─────────────────────────────────────


class TestStageResult:
    def _now(self):
        return utc_now()

    @pytest.mark.parametrize(
        "status,extra",
        [
            (StageStatus.GREEN, {}),
            (StageStatus.YELLOW, {"data_issue_summary": "one series stale"}),
            (StageStatus.RED, {"safe_error_summary": "ValueError: boom"}),
            (StageStatus.SKIPPED, {"skip_reason": "not Monday"}),
        ],
    )
    def test_all_terminal_statuses_are_accepted(self, status, extra):
        now = self._now()
        stage = StageResult(
            stage_name="fake",
            stage_type=StageType.DESK,
            started_at=now,
            ended_at=now,
            status=status,
            **extra,
        )
        assert stage.status is status

    def test_required_fields_are_present(self):
        now = self._now()
        stage = StageResult(
            stage_name="fake",
            stage_type=StageType.DESK,
            started_at=now,
            ended_at=now,
            status=StageStatus.GREEN,
        )
        for attr in (
            "stage_name",
            "stage_type",
            "started_at",
            "ended_at",
            "status",
            "artifact_references",
            "data_issue_summary",
            "validation_summary",
            "retry_count",
            "safe_error_summary",
            "skip_reason",
        ):
            assert hasattr(stage, attr)

    def test_skipped_requires_reason(self):
        now = self._now()
        with pytest.raises(ValueError):
            StageResult(
                stage_name="x",
                stage_type=StageType.DESK,
                started_at=now,
                ended_at=now,
                status=StageStatus.SKIPPED,
                skip_reason=None,
            )
        with pytest.raises(ValueError):
            StageResult(
                stage_name="x",
                stage_type=StageType.DESK,
                started_at=now,
                ended_at=now,
                status=StageStatus.SKIPPED,
                skip_reason="   ",
            )

    def test_skipped_cannot_carry_safe_error_summary(self):
        now = self._now()
        with pytest.raises(ValueError):
            StageResult(
                stage_name="x",
                stage_type=StageType.DESK,
                started_at=now,
                ended_at=now,
                status=StageStatus.SKIPPED,
                skip_reason="not Monday",
                safe_error_summary="disguised failure",
            )

    def test_red_cannot_carry_skip_reason(self):
        now = self._now()
        with pytest.raises(ValueError):
            StageResult(
                stage_name="x",
                stage_type=StageType.DESK,
                started_at=now,
                ended_at=now,
                status=StageStatus.RED,
                safe_error_summary="boom",
                skip_reason="not really skipped",
            )

    def test_red_requires_explanation(self):
        now = self._now()
        with pytest.raises(ValueError):
            StageResult(
                stage_name="x",
                stage_type=StageType.DESK,
                started_at=now,
                ended_at=now,
                status=StageStatus.RED,
            )

    def test_red_explanation_via_validation_summary(self):
        now = self._now()
        StageResult(
            stage_name="x",
            stage_type=StageType.DESK,
            started_at=now,
            ended_at=now,
            status=StageStatus.RED,
            validation_summary="12/13 validators passed; 1 hard fail",
        )

    def test_red_explanation_via_data_issue_summary(self):
        now = self._now()
        StageResult(
            stage_name="x",
            stage_type=StageType.DESK,
            started_at=now,
            ended_at=now,
            status=StageStatus.RED,
            data_issue_summary="banking input missing",
        )

    def test_green_cannot_carry_safe_error_summary(self):
        now = self._now()
        with pytest.raises(ValueError):
            StageResult(
                stage_name="x",
                stage_type=StageType.DESK,
                started_at=now,
                ended_at=now,
                status=StageStatus.GREEN,
                safe_error_summary="something failed silently",
            )

    def test_green_cannot_carry_skip_reason(self):
        now = self._now()
        with pytest.raises(ValueError):
            StageResult(
                stage_name="x",
                stage_type=StageType.DESK,
                started_at=now,
                ended_at=now,
                status=StageStatus.GREEN,
                skip_reason="anything",
            )

    def test_negative_retry_rejected(self):
        now = self._now()
        with pytest.raises(ValueError):
            StageResult(
                stage_name="x",
                stage_type=StageType.DESK,
                started_at=now,
                ended_at=now,
                status=StageStatus.GREEN,
                retry_count=-1,
            )

    def test_string_status_is_normalized(self):
        now = self._now()
        stage = StageResult(
            stage_name="x",
            stage_type="DESK",  # type: ignore[arg-type]
            started_at=now,
            ended_at=now,
            status="GREEN",  # type: ignore[arg-type]
        )
        assert stage.status is StageStatus.GREEN
        assert stage.stage_type is StageType.DESK

    def test_stage_result_is_immutable_after_construction(self):
        now = self._now()
        stage = StageResult(
            stage_name="x",
            stage_type=StageType.DESK,
            started_at=now,
            ended_at=now,
            status=StageStatus.GREEN,
        )
        # Frozen dataclass — direct attribute assignment must raise.
        with pytest.raises(Exception):
            stage.status = StageStatus.RED  # type: ignore[misc]
        # artifact_references is a tuple → not mutable via .append/.extend.
        assert isinstance(stage.artifact_references, tuple)
        with pytest.raises(AttributeError):
            stage.artifact_references.append("mutant")  # type: ignore[attr-defined]

    def test_artifact_references_input_coerced_to_tuple(self):
        now = self._now()
        stage = StageResult(
            stage_name="x",
            stage_type=StageType.DESK,
            started_at=now,
            ended_at=now,
            status=StageStatus.GREEN,
            artifact_references=["a", "b"],  # list input → coerced
        )
        assert stage.artifact_references == ("a", "b")


# ── I. Missing metadata handled gracefully ────────────────────────────────────


class TestMissingMetadata:
    def test_run_record_allows_missing_metadata(self):
        now = utc_now()
        run = RunRecord(
            run_id=generate_run_id(),
            started_at=now,
            ended_at=None,
            cadence=None,
            trigger=None,
            requested_stages=[],
            git_sha=None,
            git_branch=None,
            git_dirty=None,
            python_version=None,
            known_model_identifiers={"macro_agent": None},
            known_prompt_identifiers={"macro_prompt": None},
        )
        assert run.git_sha is None
        assert run.git_branch is None
        assert run.git_dirty is None
        assert run.python_version is None
        assert run.known_model_identifiers == {"macro_agent": None}
        assert run.known_prompt_identifiers == {"macro_prompt": None}

    def test_run_record_rejects_duplicate_requested_stages(self):
        now = utc_now()
        with pytest.raises(ValueError):
            RunRecord(
                run_id=generate_run_id(),
                started_at=now,
                ended_at=None,
                cadence=None,
                trigger=None,
                requested_stages=["macro", "macro"],
                git_sha=None,
                git_branch=None,
                git_dirty=None,
                python_version=None,
            )
