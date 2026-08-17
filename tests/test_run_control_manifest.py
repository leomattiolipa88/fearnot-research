"""Manifest round-trip, hardening, finalization and Git metadata tests.

Covers Codex Correction 3 (bijection at finalization), Correction 5
(defensive redaction at the write boundary), and Correction 6 (manifest
/ run_id / timestamp / path validation).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from run_control import (
    AggregateStatus,
    GitMetadata,
    RunFinalizationError,
    RunRecord,
    StageResult,
    StageStatus,
    StageType,
    capture_git_metadata,
    finalize_run,
    generate_run_id,
    manifest_path,
    read_manifest,
    utc_now,
    write_manifest,
)
from run_control.git_meta import _FORBIDDEN_GIT_VERBS


def _sample_run() -> RunRecord:
    now = utc_now()
    stages = [
        StageResult(
            stage_name="control",
            stage_type=StageType.CONTROL,
            started_at=now,
            ended_at=now + timedelta(milliseconds=1),
            status=StageStatus.GREEN,
            artifact_references=("logs/runs/xxx/init.log",),
        ),
        StageResult(
            stage_name="macro",
            stage_type=StageType.DESK,
            started_at=now,
            ended_at=now + timedelta(seconds=3),
            status=StageStatus.YELLOW,
            data_issue_summary="1 series stale",
            validation_summary="9/10 validators passed",
            retry_count=1,
            artifact_references=("data/tesis_2026-08-16.json",),
        ),
        StageResult(
            stage_name="synthesizer",
            stage_type=StageType.DESK,
            started_at=now,
            ended_at=now,
            status=StageStatus.SKIPPED,
            skip_reason="not Monday",
        ),
        StageResult(
            stage_name="banking",
            stage_type=StageType.DESK,
            started_at=now,
            ended_at=now + timedelta(seconds=1),
            status=StageStatus.RED,
            safe_error_summary="ValueError: expected input missing",
        ),
    ]
    return RunRecord(
        run_id=generate_run_id(),
        started_at=now,
        ended_at=now + timedelta(seconds=5),
        cadence="daily",
        trigger="cron",
        requested_stages=["control", "macro", "synthesizer", "banking"],
        git_sha="abc123",
        git_branch="fear-not-m1-run-control",
        git_dirty=False,
        python_version="3.11.3",
        known_model_identifiers={"macro_agent": "claude-opus-5"},
        known_prompt_identifiers={"macro_prompt": None},
        stage_results=stages,
        aggregate_status=AggregateStatus.YELLOW,
        publication_attempted=True,
        publication_observed_outcome="pushed",
        safe_errors=["ValueError: expected input missing"],
    )


# ── G. Manifest round-trip ────────────────────────────────────────────────────


class TestManifestRoundTrip:
    def test_serialize_and_deserialize(self, tmp_path):
        run = _sample_run()
        path = manifest_path(run.run_id, tmp_path)
        write_manifest(run, path)
        loaded = read_manifest(path)

        assert loaded.run_id == run.run_id
        assert loaded.started_at == run.started_at
        assert loaded.ended_at == run.ended_at
        assert loaded.cadence == run.cadence
        assert loaded.trigger == run.trigger
        assert loaded.requested_stages == run.requested_stages
        assert loaded.git_sha == run.git_sha
        assert loaded.git_branch == run.git_branch
        assert loaded.git_dirty == run.git_dirty
        assert loaded.python_version == run.python_version
        assert loaded.known_model_identifiers == run.known_model_identifiers
        assert loaded.known_prompt_identifiers == run.known_prompt_identifiers
        assert loaded.aggregate_status == run.aggregate_status
        assert loaded.publication_attempted == run.publication_attempted
        assert loaded.publication_observed_outcome == run.publication_observed_outcome
        assert loaded.safe_errors == run.safe_errors

        assert len(loaded.stage_results) == len(run.stage_results)
        for a, b in zip(loaded.stage_results, run.stage_results):
            assert a.stage_name == b.stage_name
            assert a.stage_type == b.stage_type
            assert a.status == b.status
            assert a.started_at == b.started_at
            assert a.ended_at == b.ended_at
            assert list(a.artifact_references) == list(b.artifact_references)
            assert a.data_issue_summary == b.data_issue_summary
            assert a.validation_summary == b.validation_summary
            assert a.retry_count == b.retry_count
            assert a.safe_error_summary == b.safe_error_summary
            assert a.skip_reason == b.skip_reason

    def test_manifest_is_valid_json(self, tmp_path):
        run = _sample_run()
        path = manifest_path(run.run_id, tmp_path)
        write_manifest(run, path)
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert parsed["run_id"] == run.run_id
        assert parsed["schema_version"] == 1
        assert parsed["aggregate_status"] == "YELLOW"

    def test_manifest_path_lives_under_runs_subdir(self, tmp_path):
        run = _sample_run()
        expected = (tmp_path / "runs" / run.run_id / "manifest.json").resolve()
        assert manifest_path(run.run_id, tmp_path) == expected

    def test_double_round_trip_is_stable(self, tmp_path):
        run = _sample_run()
        p1 = manifest_path(run.run_id, tmp_path)
        write_manifest(run, p1)
        first = read_manifest(p1)
        p2 = tmp_path / "second.json"
        write_manifest(first, p2)
        assert p1.read_text() == p2.read_text()


# ── Finalization / bijection (Correction 3) ──────────────────────────────────


class TestFinalization:
    def _base_run(self, tmp_path):
        run = _sample_run()
        return run, manifest_path(run.run_id, tmp_path)

    def test_missing_result_rejected(self, tmp_path):
        run, path = self._base_run(tmp_path)
        run.requested_stages.append("web_exporter")  # not in results
        with pytest.raises(RunFinalizationError):
            finalize_run(run)
        with pytest.raises(RunFinalizationError):
            write_manifest(run, path)
        assert not path.exists()

    def test_unknown_result_rejected(self, tmp_path):
        run, path = self._base_run(tmp_path)
        now = utc_now()
        run.stage_results.append(
            StageResult(
                stage_name="ghost",
                stage_type=StageType.DESK,
                started_at=now,
                ended_at=now,
                status=StageStatus.GREEN,
            )
        )
        with pytest.raises(RunFinalizationError):
            finalize_run(run)

    def test_duplicate_result_rejected(self, tmp_path):
        run, path = self._base_run(tmp_path)
        # Duplicate the first stage result.
        run.stage_results.append(run.stage_results[0])
        with pytest.raises(RunFinalizationError):
            finalize_run(run)

    def test_missing_aggregate_status_rejected(self, tmp_path):
        run, path = self._base_run(tmp_path)
        run.aggregate_status = None
        with pytest.raises(RunFinalizationError):
            finalize_run(run)

    def test_duplicate_requested_at_construction_time(self):
        now = utc_now()
        with pytest.raises(ValueError):
            RunRecord(
                run_id=generate_run_id(),
                started_at=now,
                ended_at=now,
                cadence=None,
                trigger=None,
                requested_stages=["macro", "macro"],
                git_sha=None,
                git_branch=None,
                git_dirty=None,
                python_version=None,
            )


# ── Correction 5: defensive redaction at the write boundary ──────────────────


FAKE = "sk-ant-FAKE-BOUNDARY-secretvalueXYZ0123456789"
FAKE_HEADER = "Authorization: Bearer FAKE-HEADER-abcdefghijk123456"


class TestManifestRedactionBoundary:
    def _build_run_with_secret_fields(self):
        now = utc_now()
        # StageResult constructor rejects safe_error_summary on GREEN, so the
        # only way to plant a secret into a terminal record is on RED — which
        # is the exact path a real failure takes.
        stage = StageResult(
            stage_name="banking",
            stage_type=StageType.DESK,
            started_at=now,
            ended_at=now,
            status=StageStatus.RED,
            safe_error_summary=f"crashed: {FAKE} {FAKE_HEADER}",
            data_issue_summary=f"nested leak: {FAKE}",
            validation_summary=f"header leak: {FAKE_HEADER}",
        )
        return RunRecord(
            run_id=generate_run_id(),
            started_at=now,
            ended_at=now,
            cadence="daily",
            trigger="test",
            requested_stages=["banking"],
            git_sha=None,
            git_branch=None,
            git_dirty=None,
            python_version=None,
            stage_results=[stage],
            aggregate_status=AggregateStatus.YELLOW,
            safe_errors=[f"top-level leak: {FAKE}", f"top-level header: {FAKE_HEADER}"],
        )

    def test_manifest_scrubs_stage_error_fields(self, tmp_path):
        run = self._build_run_with_secret_fields()
        path = manifest_path(run.run_id, tmp_path)
        write_manifest(run, path, extra_secret_values=[FAKE, FAKE_HEADER])
        raw = path.read_text(encoding="utf-8")
        assert FAKE not in raw
        assert "FAKE-HEADER-abcdefghijk" not in raw

    def test_manifest_scrubs_top_level_safe_errors(self, tmp_path):
        run = self._build_run_with_secret_fields()
        path = manifest_path(run.run_id, tmp_path)
        write_manifest(run, path, extra_secret_values=[FAKE, FAKE_HEADER])
        loaded = read_manifest(path)
        for entry in loaded.safe_errors:
            assert FAKE not in entry
            assert "FAKE-HEADER-abcdefghijk" not in entry

    def test_manifest_scrubs_direct_stage_safe_error_summary(self, tmp_path):
        run = self._build_run_with_secret_fields()
        path = manifest_path(run.run_id, tmp_path)
        write_manifest(run, path, extra_secret_values=[FAKE, FAKE_HEADER])
        loaded = read_manifest(path)
        for st in loaded.stage_results:
            assert not (st.safe_error_summary and FAKE in st.safe_error_summary)
            assert not (st.data_issue_summary and FAKE in st.data_issue_summary)
            assert not (
                st.validation_summary
                and "FAKE-HEADER-abcdefghijk" in st.validation_summary
            )


# ── Correction 6: manifest schema / timestamp / run_id / path validation ──────


class TestManifestHardening:
    def _write_manifest_and_tamper(self, tmp_path, mutate):
        run = _sample_run()
        path = manifest_path(run.run_id, tmp_path)
        write_manifest(run, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        mutate(data)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_missing_schema_version_rejected(self, tmp_path):
        path = self._write_manifest_and_tamper(
            tmp_path, lambda d: d.pop("schema_version")
        )
        with pytest.raises(ValueError):
            read_manifest(path)

    def test_unsupported_schema_version_rejected(self, tmp_path):
        path = self._write_manifest_and_tamper(
            tmp_path, lambda d: d.__setitem__("schema_version", 999)
        )
        with pytest.raises(ValueError):
            read_manifest(path)

    def test_naive_timestamp_rejected(self, tmp_path):
        path = self._write_manifest_and_tamper(
            tmp_path,
            lambda d: d.__setitem__("started_at", "2026-08-16T14:01:02"),
        )
        with pytest.raises(ValueError):
            read_manifest(path)

    def test_invalid_run_id_rejected_on_read(self, tmp_path):
        path = self._write_manifest_and_tamper(
            tmp_path,
            lambda d: d.__setitem__("run_id", "NOT-A-VALID-ID"),
        )
        with pytest.raises(ValueError):
            read_manifest(path)

    def test_impossible_date_run_id_rejected_on_read(self, tmp_path):
        # Shape matches but 02-32 is impossible.
        path = self._write_manifest_and_tamper(
            tmp_path,
            lambda d: d.__setitem__(
                "run_id", "FN-20260232T140102Z-abcdef01"
            ),
        )
        with pytest.raises(ValueError):
            read_manifest(path)

    def test_manifest_path_refuses_invalid_run_id(self, tmp_path):
        with pytest.raises(ValueError):
            manifest_path("../escape", tmp_path)
        with pytest.raises(ValueError):
            manifest_path("FN-20260816T140102Z-", tmp_path)
        with pytest.raises(ValueError):
            manifest_path("bogus", tmp_path)

    def test_manifest_path_stays_under_base_dir(self, tmp_path):
        # A valid run_id cannot escape (validator would reject anything with
        # slashes / dots), but assert the defense-in-depth check works.
        rid = generate_run_id()
        p = manifest_path(rid, tmp_path)
        p.relative_to(tmp_path.resolve())


# ── Correction C (pass 2): no silent manifest field loss ─────────────────────


class TestManifestUnknownFields:
    """A manifest read that silently drops unknown fields would lose data on
    a read → write cycle. schema_version=1 requires strict rejection.
    """

    def _write(self, tmp_path, mutate):
        run = _sample_run()
        path = manifest_path(run.run_id, tmp_path)
        write_manifest(run, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        mutate(data)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_unknown_top_level_field_rejected(self, tmp_path):
        path = self._write(
            tmp_path,
            lambda d: d.__setitem__(
                "future_field_that_does_not_exist", "some value"
            ),
        )
        with pytest.raises(ValueError) as ei:
            read_manifest(path)
        assert "unknown top-level fields" in str(ei.value)
        assert "future_field_that_does_not_exist" in str(ei.value)

    def test_unknown_stage_result_field_rejected(self, tmp_path):
        def mutate(d):
            d["stage_results"][0]["future_stage_field"] = "nope"

        path = self._write(tmp_path, mutate)
        with pytest.raises(ValueError) as ei:
            read_manifest(path)
        assert "unknown fields" in str(ei.value)
        assert "future_stage_field" in str(ei.value)

    def test_valid_current_manifest_still_round_trips(self, tmp_path):
        """The strict allow-list must not break the declared field set."""
        run = _sample_run()
        path = manifest_path(run.run_id, tmp_path)
        write_manifest(run, path)
        # No mutation — must round-trip cleanly.
        loaded = read_manifest(path)
        assert loaded.run_id == run.run_id
        assert loaded.aggregate_status == run.aggregate_status
        # And the write→read→write cycle is stable byte-for-byte.
        second = tmp_path / "second.json"
        write_manifest(loaded, second)
        assert path.read_text() == second.read_text()

    def test_no_silent_data_loss_between_read_and_write(self, tmp_path):
        """Concretely proves that no read path can strip a top-level field
        that write would then omit — because unknown fields are rejected,
        not silently discarded."""
        run = _sample_run()
        path = manifest_path(run.run_id, tmp_path)
        write_manifest(run, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        # Verify every declared field survives serialization.
        declared = {
            "schema_version",
            "run_id",
            "started_at",
            "ended_at",
            "cadence",
            "trigger",
            "requested_stages",
            "git_sha",
            "git_branch",
            "git_dirty",
            "python_version",
            "known_model_identifiers",
            "known_prompt_identifiers",
            "stage_results",
            "aggregate_status",
            "publication_attempted",
            "publication_observed_outcome",
            "safe_errors",
        }
        assert declared <= set(data.keys())


# ── H. Git metadata capture ──────────────────────────────────────────────────


def _git_available() -> bool:
    try:
        subprocess.run(
            ["git", "--version"], capture_output=True, timeout=3, check=False
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _git_available(), reason="git CLI not available")
class TestGitMetadata:
    def _init_repo(self, path: Path) -> None:
        init = subprocess.run(
            ["git", "init", "-q", "-b", "main", str(path)],
            capture_output=True,
            check=False,
        )
        if init.returncode != 0:
            subprocess.run(
                ["git", "init", "-q", str(path)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(path), "symbolic-ref", "HEAD", "refs/heads/main"],
                check=True,
                capture_output=True,
            )
        subprocess.run(
            ["git", "-C", str(path), "config", "user.email", "test@example.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        (path / "readme.txt").write_text("hi\n")
        subprocess.run(
            ["git", "-C", str(path), "add", "readme.txt"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "commit", "-q", "-m", "init"],
            check=True,
            capture_output=True,
        )

    def test_captures_sha_branch_clean(self, tmp_path):
        self._init_repo(tmp_path)
        meta = capture_git_metadata(tmp_path)
        assert isinstance(meta, GitMetadata)
        assert meta.sha and len(meta.sha) == 40
        assert meta.branch == "main"
        assert meta.dirty is False

    def test_detects_dirty_state(self, tmp_path):
        self._init_repo(tmp_path)
        (tmp_path / "readme.txt").write_text("changed\n")
        meta = capture_git_metadata(tmp_path)
        assert meta.dirty is True

    def test_returns_none_outside_a_repo(self, tmp_path):
        meta = capture_git_metadata(tmp_path)
        assert meta.sha is None
        assert meta.branch is None
        assert meta.dirty is None

    def test_forbidden_verbs_are_deny_listed(self):
        for verb in (
            "add",
            "commit",
            "tag",
            "push",
            "pull",
            "fetch",
            "reset",
            "restore",
            "checkout",
            "merge",
            "rebase",
            "clean",
        ):
            assert verb in _FORBIDDEN_GIT_VERBS

    def test_capture_only_uses_read_only_verbs(self, tmp_path, monkeypatch):
        self._init_repo(tmp_path)
        seen_verbs: list[str] = []
        real_run = subprocess.run

        def spy(cmd, *args, **kwargs):
            if isinstance(cmd, list) and cmd and cmd[0] == "git":
                if len(cmd) > 1:
                    seen_verbs.append(cmd[1])
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(subprocess, "run", spy)
        capture_git_metadata(tmp_path)
        assert seen_verbs, "expected at least one git invocation"
        for verb in seen_verbs:
            assert verb not in _FORBIDDEN_GIT_VERBS, verb
            assert verb in {"rev-parse", "status"}

    def test_run_helper_refuses_forbidden_verbs(self, tmp_path):
        from run_control.git_meta import _run

        for verb in ("commit", "push", "reset", "clean"):
            with pytest.raises(AssertionError):
                _run(["git", verb], tmp_path)
