"""Operator-facing CLI tests (Correction A, pass 2).

Verifies that a naive operator running the wrapper from the terminal
cannot mistake a SYSTEM RED run for a successful one — the exit code
carries the outcome and the manifest is written before that outcome is
signalled.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from run_control import (
    EXIT_MANIFEST_FAILURE,
    EXIT_OK,
    EXIT_SYSTEM_RED,
    AggregateStatus,
    DailyRunConfig,
    ProcessOutcome,
    RunRecord,
    StageResult,
    StageStatus,
    StageType,
    cli_run,
    derive_exit_code,
    generate_run_id,
    has_execution_failure,
    manifest_path,
    utc_now,
)

REPO_ROOT = Path(__file__).parent.parent


# Local FakeRunner (duplicated intentionally from the wrapper suite so this
# file stands alone — no cross-test-file fixture coupling).
class _FakeRunner:
    def __init__(self, plan: dict[str, ProcessOutcome] | None = None):
        self.plan = dict(plan or {})
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def __call__(self, name, argv):
        self.calls.append((name, tuple(argv)))
        return self.plan.get(name, ProcessOutcome(returncode=0))


def _config(tmp_path, runner):
    return DailyRunConfig(
        repo_root=REPO_ROOT,
        logs_dir=tmp_path,
        is_monday=False,
        trigger="cli-test",
        process_runner=runner,
    )


def _fake_run(aggregate: AggregateStatus) -> RunRecord:
    """Build a minimal well-formed RunRecord with a chosen aggregate."""
    now = utc_now()
    # For RED aggregates, seed a single RED stage so it is consistent.
    if aggregate is AggregateStatus.RED:
        stage = StageResult(
            stage_name="s1",
            stage_type=StageType.CONTROL,
            started_at=now,
            ended_at=now + timedelta(milliseconds=1),
            status=StageStatus.RED,
            safe_error_summary="test-driven RED",
        )
    elif aggregate is AggregateStatus.YELLOW:
        stage = StageResult(
            stage_name="s1",
            stage_type=StageType.DESK,
            started_at=now,
            ended_at=now,
            status=StageStatus.YELLOW,
            data_issue_summary="degraded",
        )
    else:
        stage = StageResult(
            stage_name="s1",
            stage_type=StageType.SUPPORT,
            started_at=now,
            ended_at=now,
            status=StageStatus.GREEN,
        )
    return RunRecord(
        run_id=generate_run_id(),
        started_at=now,
        ended_at=now,
        cadence="daily",
        trigger="test",
        requested_stages=["s1"],
        git_sha=None,
        git_branch=None,
        git_dirty=None,
        python_version="3.11.3",
        stage_results=[stage],
        aggregate_status=aggregate,
    )


# ── derive_exit_code (pure) ───────────────────────────────────────────────────


class TestDeriveExitCode:
    def test_green_yields_zero(self):
        assert derive_exit_code(_fake_run(AggregateStatus.GREEN)) == EXIT_OK

    def test_pure_semantic_yellow_yields_zero(self):
        """YELLOW aggregate produced only by non-fatal YELLOW stage
        statuses (no RED stage anywhere) is a "usable-but-degraded" run
        and must exit 0."""
        run = _fake_run(AggregateStatus.YELLOW)
        assert not has_execution_failure(run)
        assert derive_exit_code(run) == EXIT_OK

    def test_red_aggregate_yields_nonzero(self):
        assert derive_exit_code(_fake_run(AggregateStatus.RED)) == EXIT_SYSTEM_RED

    def test_yellow_aggregate_with_red_stage_yields_nonzero(self):
        """The intentional aggregation maps a lone SUPPORT-stage RED to
        SYSTEM YELLOW, but the operator must still see nonzero because a
        child subprocess actually failed."""
        now = utc_now()
        run = RunRecord(
            run_id=generate_run_id(),
            started_at=now,
            ended_at=now,
            cadence="daily",
            trigger="test",
            requested_stages=["support_thing", "macro_agent"],
            git_sha=None,
            git_branch=None,
            git_dirty=None,
            python_version=None,
            stage_results=[
                StageResult(
                    stage_name="support_thing",
                    stage_type=StageType.SUPPORT,
                    started_at=now,
                    ended_at=now,
                    status=StageStatus.RED,
                    safe_error_summary="child returncode=1",
                ),
                StageResult(
                    stage_name="macro_agent",
                    stage_type=StageType.DESK,
                    started_at=now,
                    ended_at=now,
                    status=StageStatus.GREEN,
                ),
            ],
            aggregate_status=AggregateStatus.YELLOW,
        )
        assert has_execution_failure(run) is True
        assert derive_exit_code(run) == EXIT_SYSTEM_RED


# ── cli_run (integration with the daily wrapper) ─────────────────────────────


class TestCliRun:
    def test_all_green_exits_zero(self, tmp_path):
        runner = _FakeRunner()
        exit_code, run = cli_run(_config(tmp_path, runner))
        assert run is not None
        assert run.aggregate_status is AggregateStatus.GREEN
        assert exit_code == EXIT_OK
        assert manifest_path(run.run_id, tmp_path).exists()

    def test_ordinary_child_failure_exits_nonzero(self, tmp_path):
        runner = _FakeRunner(
            plan={
                "macro_collector": ProcessOutcome(
                    returncode=1, stderr="fred outage"
                )
            }
        )
        exit_code, run = cli_run(_config(tmp_path, runner))
        assert run is not None
        assert exit_code == EXIT_SYSTEM_RED
        # Manifest was written BEFORE the exit code was surfaced.
        assert manifest_path(run.run_id, tmp_path).exists()

    def test_health_check_red_exits_nonzero(self, tmp_path):
        runner = _FakeRunner(
            plan={
                "health_check": ProcessOutcome(
                    returncode=1, stderr="thesis file missing"
                )
            }
        )
        exit_code, run = cli_run(_config(tmp_path, runner))
        assert run is not None
        assert exit_code == EXIT_SYSTEM_RED
        # health_check is CONTROL → aggregate → SYSTEM RED
        assert run.aggregate_status is AggregateStatus.RED
        assert manifest_path(run.run_id, tmp_path).exists()

    def test_manifest_exists_before_red_is_surfaced(self, tmp_path):
        """A recording process runner asserts that the manifest is written
        as a *side effect of run_daily* — the exit code is derived from the
        finalized record, not from an in-flight state."""
        runner = _FakeRunner(
            plan={"macro_agent": ProcessOutcome(returncode=1, stderr="boom")}
        )
        exit_code, run = cli_run(_config(tmp_path, runner))
        assert run is not None
        path = manifest_path(run.run_id, tmp_path)
        assert path.exists(), "manifest must exist before exit code is surfaced"
        assert exit_code == EXIT_SYSTEM_RED

    def test_support_child_failure_exits_nonzero_even_if_aggregate_yellow(
        self, tmp_path
    ):
        """Regression from Correction Pass 2: SUPPORT stage failure yields
        YELLOW aggregate (per audit-validated aggregation), but the CLI
        must still exit nonzero because a real child process failed."""
        runner = _FakeRunner(
            plan={
                "news_collector": ProcessOutcome(
                    returncode=1, stderr="newsapi outage"
                )
            }
        )
        exit_code, run = cli_run(_config(tmp_path, runner))
        assert run is not None
        # Aggregate is YELLOW (SUPPORT RED, desks all become SKIPPED via the
        # cascade abort; no desk RED so no all-desks-dead trigger).
        assert run.aggregate_status is AggregateStatus.YELLOW
        # But a real subprocess failed — exit must be nonzero.
        assert exit_code == EXIT_SYSTEM_RED
        assert manifest_path(run.run_id, tmp_path).exists()

    def test_desk_child_failure_exits_nonzero(self, tmp_path):
        runner = _FakeRunner(
            plan={
                "og_agent": ProcessOutcome(
                    returncode=1, stderr="anthropic 503"
                )
            }
        )
        exit_code, run = cli_run(_config(tmp_path, runner))
        assert run is not None
        assert exit_code == EXIT_SYSTEM_RED
        assert manifest_path(run.run_id, tmp_path).exists()

    def test_wrapper_finalization_failure_returns_two(self, monkeypatch, tmp_path):
        """If write_manifest itself raises (e.g. finalization violation), the
        CLI returns EXIT_MANIFEST_FAILURE — a distinct outcome from ordinary
        SYSTEM RED so operators know NOTHING was persisted."""

        def boom(*args, **kwargs):
            raise RuntimeError("simulated finalization failure")

        # Patch run_daily so that no manifest is written.
        import run_control.cli as cli_mod

        monkeypatch.setattr(cli_mod, "run_daily", boom)
        exit_code, run = cli_run(_config(tmp_path, _FakeRunner()))
        assert exit_code == EXIT_MANIFEST_FAILURE
        assert run is None
