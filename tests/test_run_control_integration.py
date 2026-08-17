"""Controlled fake-pipeline integration tests — no network, no external services."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from run_control import (
    AggregateStatus,
    RunRecord,
    StageStatus,
    StageType,
    aggregate_status,
    execute_stage,
    generate_run_id,
    manifest_path,
    read_manifest,
    skipped_stage,
    utc_now,
    write_manifest,
)


def _run_fake_pipeline(stages_spec: list[dict]) -> RunRecord:
    """Drive a fake pipeline through the M1 envelope only.

    Each entry in ``stages_spec`` is a dict with ``name``, ``type``,
    ``mode`` in ('success','yellow','fail','skip'), and (for 'skip')
    a ``skip_reason``.
    """
    run_id = generate_run_id()
    started = utc_now()
    results = []
    for spec in stages_spec:
        name = spec["name"]
        stype = spec["type"]
        mode = spec["mode"]
        if mode == "skip":
            results.append(skipped_stage(name, stype, spec["skip_reason"]))
            continue
        if mode == "success":
            fn = lambda: None  # noqa: E731
        elif mode == "yellow":
            fn = lambda: StageStatus.YELLOW  # noqa: E731
        elif mode == "fail":
            def fn(msg=spec.get("error", "boom")):
                raise RuntimeError(msg)
        else:
            raise AssertionError(f"unknown mode {mode!r}")
        results.append(execute_stage(name, stype, fn))
    ended = utc_now()
    return RunRecord(
        run_id=run_id,
        started_at=started,
        ended_at=ended,
        cadence="daily",
        trigger="test",
        requested_stages=[s["name"] for s in stages_spec],
        git_sha=None,
        git_branch=None,
        git_dirty=None,
        python_version="3.11.3",
        stage_results=results,
        aggregate_status=aggregate_status(results),
    )


class TestFakePipelineIntegration:
    def test_all_green_pipeline_end_to_end(self, tmp_path):
        run = _run_fake_pipeline(
            [
                {"name": "control", "type": StageType.CONTROL, "mode": "success"},
                {"name": "macro", "type": StageType.DESK, "mode": "success"},
                {"name": "technical", "type": StageType.DESK, "mode": "success"},
                {"name": "energy", "type": StageType.DESK, "mode": "success"},
                {"name": "web", "type": StageType.PUBLICATION, "mode": "success"},
            ]
        )
        assert run.aggregate_status is AggregateStatus.GREEN
        path = manifest_path(run.run_id, tmp_path)
        write_manifest(run, path)
        reloaded = read_manifest(path)
        assert reloaded.aggregate_status is AggregateStatus.GREEN
        assert all(s.status is StageStatus.GREEN for s in reloaded.stage_results)

    def test_failed_desk_pipeline(self, tmp_path):
        run = _run_fake_pipeline(
            [
                {"name": "control", "type": StageType.CONTROL, "mode": "success"},
                {"name": "macro", "type": StageType.DESK, "mode": "fail"},
                {"name": "technical", "type": StageType.DESK, "mode": "success"},
            ]
        )
        assert run.aggregate_status is AggregateStatus.YELLOW
        macro = next(s for s in run.stage_results if s.stage_name == "macro")
        assert macro.status is StageStatus.RED
        assert macro.safe_error_summary is not None
        # Round-trip preserves the failure.
        path = manifest_path(run.run_id, tmp_path)
        write_manifest(run, path)
        reloaded = read_manifest(path)
        reloaded_macro = next(
            s for s in reloaded.stage_results if s.stage_name == "macro"
        )
        assert reloaded_macro.status is StageStatus.RED

    def test_skipped_stage_pipeline(self, tmp_path):
        run = _run_fake_pipeline(
            [
                {"name": "control", "type": StageType.CONTROL, "mode": "success"},
                {"name": "macro", "type": StageType.DESK, "mode": "success"},
                {
                    "name": "synthesizer",
                    "type": StageType.DESK,
                    "mode": "skip",
                    "skip_reason": "not Monday",
                },
                {"name": "web", "type": StageType.PUBLICATION, "mode": "success"},
            ]
        )
        assert run.aggregate_status is AggregateStatus.GREEN
        synth = next(
            s for s in run.stage_results if s.stage_name == "synthesizer"
        )
        assert synth.status is StageStatus.SKIPPED
        assert synth.skip_reason == "not Monday"
        # Persist & reload preserves skip_reason.
        path = manifest_path(run.run_id, tmp_path)
        write_manifest(run, path)
        reloaded = read_manifest(path)
        reloaded_synth = next(
            s for s in reloaded.stage_results if s.stage_name == "synthesizer"
        )
        assert reloaded_synth.skip_reason == "not Monday"

    def test_mixed_status_pipeline(self, tmp_path):
        run = _run_fake_pipeline(
            [
                {"name": "control", "type": StageType.CONTROL, "mode": "success"},
                {"name": "macro", "type": StageType.DESK, "mode": "success"},
                {"name": "technical", "type": StageType.DESK, "mode": "yellow"},
                {"name": "energy", "type": StageType.DESK, "mode": "fail"},
                {
                    "name": "synthesizer",
                    "type": StageType.DESK,
                    "mode": "skip",
                    "skip_reason": "not Monday",
                },
                {"name": "web", "type": StageType.PUBLICATION, "mode": "success"},
            ]
        )
        assert run.aggregate_status is AggregateStatus.YELLOW
        by_name = {s.stage_name: s for s in run.stage_results}
        assert by_name["macro"].status is StageStatus.GREEN
        assert by_name["technical"].status is StageStatus.YELLOW
        assert by_name["energy"].status is StageStatus.RED
        assert by_name["synthesizer"].status is StageStatus.SKIPPED
        assert by_name["web"].status is StageStatus.GREEN
        # Round-trip preserves the full mixed picture.
        path = manifest_path(run.run_id, tmp_path)
        write_manifest(run, path)
        reloaded = read_manifest(path)
        assert reloaded.aggregate_status is AggregateStatus.YELLOW
        assert (
            [s.status for s in reloaded.stage_results]
            == [s.status for s in run.stage_results]
        )

    def test_manifest_default_location_is_under_logs_runs(self, tmp_path):
        """Confirms the conventional location: `logs/runs/<run_id>/manifest.json`."""
        run = _run_fake_pipeline(
            [
                {"name": "control", "type": StageType.CONTROL, "mode": "success"},
            ]
        )
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        path = manifest_path(run.run_id, logs_dir)
        # Resolve both sides so a symlinked /tmp on macOS doesn't false-negative.
        assert path.parent.parent == (logs_dir / "runs").resolve()
        assert path.name == "manifest.json"
        assert path.parent.name == run.run_id
        write_manifest(run, path)
        assert path.exists()
