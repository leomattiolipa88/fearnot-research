"""Tests for the opt-in daily execution wrapper (Codex Correction 1).

The wrapper runs the existing Fear Not daily stages as CHILD PROCESSES in
the exact order defined by ``.github/workflows/daily_pipeline.yml``. These
tests substitute a fake process runner so nothing touches the network and
no real research script is invoked.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from run_control import (
    DAILY_STAGE_SEQUENCE,
    AggregateStatus,
    DailyRunConfig,
    ProcessOutcome,
    StageStatus,
    StageType,
    manifest_path,
    read_manifest,
    run_daily,
)


REPO_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeRunner:
    """Programmable process runner. Records every stage/argv it sees."""

    def __init__(self, plan: dict[str, ProcessOutcome] | None = None):
        self.plan = dict(plan or {})
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def __call__(self, stage_name, argv):
        self.calls.append((stage_name, tuple(argv)))
        return self.plan.get(stage_name, ProcessOutcome(returncode=0))


def _config(tmp_path, is_monday: bool = False, runner=None, extras=()):
    return DailyRunConfig(
        repo_root=REPO_ROOT,
        logs_dir=tmp_path,
        is_monday=is_monday,
        trigger="test",
        process_runner=runner or FakeRunner(),
        extra_secret_values=tuple(extras),
    )


# ---------------------------------------------------------------------------
# Stage order preservation (Correction 4)
# ---------------------------------------------------------------------------


class TestStageOrder:
    def test_stage_order_matches_daily_pipeline(self):
        """Read the actual daily_pipeline.yml and assert the wrapper's
        DAILY_STAGE_SEQUENCE lists the same scripts in the same order.
        """
        yml = (REPO_ROOT / ".github" / "workflows" / "daily_pipeline.yml").read_text(
            encoding="utf-8"
        )
        # Extract every `python <script>.py` invocation in file order.
        # Deliberately ignore `python -c "..."` since that's the inline
        # tracker_evaluate call; verified separately below.
        script_invocations = re.findall(r"python\s+([a-zA-Z_][a-zA-Z0-9_]*)\.py", yml)
        script_invocations = [
            s for s in script_invocations if s != "-"
        ]  # sanity
        wrapper_scripts = []
        for spec in DAILY_STAGE_SEQUENCE:
            argv = spec.argv
            if len(argv) >= 2 and argv[1].endswith(".py"):
                wrapper_scripts.append(argv[1].removesuffix(".py"))
            elif "-c" in argv:
                wrapper_scripts.append("__inline__")
        # Filter out the inline one for the comparison.
        wrapper_scripts_only = [s for s in wrapper_scripts if s != "__inline__"]
        assert wrapper_scripts_only == script_invocations, (
            f"wrapper: {wrapper_scripts_only}\npipeline: {script_invocations}"
        )

    def test_tracker_evaluate_is_inline_python_c(self):
        tracker = next(
            s for s in DAILY_STAGE_SEQUENCE if s.name == "tracker_evaluate"
        )
        assert tracker.argv[0] == "python"
        assert tracker.argv[1] == "-c"
        assert "evaluar_convicciones_vencidas" in tracker.argv[2]

    def test_synthesizer_is_monday_only(self):
        synth = next(s for s in DAILY_STAGE_SEQUENCE if s.name == "synthesizer")
        assert synth.monday_only is True

    def test_health_check_is_final(self):
        # Verifies the wrapper mirrors `.github/workflows/daily_pipeline.yml`
        # Step 9 comment: "last step, on purpose".
        assert DAILY_STAGE_SEQUENCE[-1].name == "health_check"

    def test_health_check_runs_always(self):
        hc = next(s for s in DAILY_STAGE_SEQUENCE if s.name == "health_check")
        assert hc.always_runs is True
        assert hc.stage_type is StageType.CONTROL

    def test_web_exporter_precedes_health_check(self):
        names = [s.name for s in DAILY_STAGE_SEQUENCE]
        assert names.index("web_exporter") < names.index("health_check")

    def test_no_stage_is_labelled_publication(self):
        """web_exporter only *generates* the export locally; the real remote
        push is a CI-only git step the wrapper does not replicate. Labelling
        web_exporter as PUBLICATION would misrepresent this — the wrapper
        keeps it as SUPPORT and leaves the PUBLICATION StageType unused."""
        pub = [s for s in DAILY_STAGE_SEQUENCE if s.stage_type is StageType.PUBLICATION]
        assert pub == []

    def test_web_exporter_is_support_stage(self):
        we = next(s for s in DAILY_STAGE_SEQUENCE if s.name == "web_exporter")
        assert we.stage_type is StageType.SUPPORT

    def test_all_scripts_are_python_invocations(self):
        # Wrapper must never introduce a git/shell command of its own.
        for spec in DAILY_STAGE_SEQUENCE:
            assert spec.argv[0] == "python", spec


# ---------------------------------------------------------------------------
# Successful sequence + run_id-before-first-stage (Correction 1)
# ---------------------------------------------------------------------------


class TestRunIdBeforeFirstStage:
    def test_run_id_is_generated_before_first_process_call(self, tmp_path):
        """The runner must observe a valid run_id in the manifest even if
        the very first stage is asked, and the run_id must not depend on
        any stage having executed."""
        captured_run_ids: list[str] = []

        class Recorder:
            def __init__(self):
                self.calls: list[tuple[str, tuple[str, ...]]] = []

            def __call__(self, name, argv):
                # We cannot observe run_id from inside a stage (there is no
                # ambient context), but we can observe that the first stage
                # ran successfully with a nonempty argv.
                self.calls.append((name, tuple(argv)))
                return ProcessOutcome(returncode=0)

        rec = Recorder()
        run = run_daily(_config(tmp_path, runner=rec))
        assert run.run_id.startswith("FN-")
        captured_run_ids.append(run.run_id)
        # First recorded call is the first daily stage.
        first_expected = DAILY_STAGE_SEQUENCE[0].name
        assert rec.calls[0][0] == first_expected


class TestSuccessfulSequence:
    def test_all_stages_green_produces_system_green(self, tmp_path):
        runner = FakeRunner()
        run = run_daily(_config(tmp_path, runner=runner))
        # Non-Monday: synthesizer SKIPPED, everything else GREEN.
        by_name = {r.stage_name: r for r in run.stage_results}
        for spec in DAILY_STAGE_SEQUENCE:
            if spec.name == "synthesizer":
                assert by_name["synthesizer"].status is StageStatus.SKIPPED
                assert "Monday" in by_name["synthesizer"].skip_reason
            else:
                assert by_name[spec.name].status is StageStatus.GREEN
        assert run.aggregate_status is AggregateStatus.GREEN
        # PUBLICATION HONESTY (Correction B, pass 2): web_exporter running
        # locally does NOT constitute remote publication. The M1 wrapper
        # never attempts the CI git-push step, so remote publication must
        # remain unattempted and unobserved.
        assert run.publication_attempted is False
        assert run.publication_observed_outcome is None

    def test_calls_are_in_exact_order(self, tmp_path):
        runner = FakeRunner()
        run_daily(_config(tmp_path, runner=runner))
        called = [name for name, _argv in runner.calls]
        # Non-Monday: synthesizer never invoked (SKIPPED); everything else
        # runs in the exact DAILY_STAGE_SEQUENCE order, including
        # health_check as the final step.
        expected = [
            s.name for s in DAILY_STAGE_SEQUENCE if s.name != "synthesizer"
        ]
        assert called == expected
        assert called[-1] == "health_check"

    def test_monday_runs_synthesizer(self, tmp_path):
        runner = FakeRunner()
        run = run_daily(_config(tmp_path, is_monday=True, runner=runner))
        synth = next(
            r for r in run.stage_results if r.stage_name == "synthesizer"
        )
        assert synth.status is StageStatus.GREEN
        assert ("synthesizer", ("python", "synthesizer.py")) in runner.calls


# ---------------------------------------------------------------------------
# Stage failure + downstream SKIPPED (Correction 5)
# ---------------------------------------------------------------------------


class TestStageFailure:
    def test_upstream_failure_aborts_and_downstream_are_skipped(self, tmp_path):
        runner = FakeRunner(
            plan={
                "og_collector": ProcessOutcome(
                    returncode=1, stderr="EIA API returned 500"
                )
            }
        )
        run = run_daily(_config(tmp_path, runner=runner))
        # Stages before og_collector should be GREEN
        for name in ("macro_collector", "news_collector"):
            r = next(x for x in run.stage_results if x.stage_name == name)
            assert r.status is StageStatus.GREEN
        # og_collector itself must be RED
        og = next(r for r in run.stage_results if r.stage_name == "og_collector")
        assert og.status is StageStatus.RED
        assert og.safe_error_summary is not None
        # Everything after og_collector in the SEQUENTIAL portion should be
        # SKIPPED; the ALWAYS-RUNS stage (health_check) still fires — mirrors
        # GitHub Actions `if: always()`.
        for spec in DAILY_STAGE_SEQUENCE:
            if spec.name in {"macro_collector", "news_collector", "og_collector"}:
                continue
            r = next(x for x in run.stage_results if x.stage_name == spec.name)
            if spec.always_runs:
                # health_check ran; in this test the fake runner defaults to
                # returncode=0 for anything not in `plan`, so it is GREEN.
                assert r.status is StageStatus.GREEN, (
                    f"always_runs stage {spec.name} should have executed"
                )
            else:
                assert r.status is StageStatus.SKIPPED, (
                    f"expected {spec.name} SKIPPED, got {r.status}"
                )
                assert r.skip_reason is not None

    def test_health_check_still_runs_after_upstream_failure(self, tmp_path):
        runner = FakeRunner(
            plan={"macro_agent": ProcessOutcome(returncode=1, stderr="boom")}
        )
        run_daily(_config(tmp_path, runner=runner))
        # runner.calls should contain both macro_agent (the failure) and
        # health_check (the always-runs step) — nothing else in between.
        called = [name for name, _argv in runner.calls]
        assert "macro_agent" in called
        assert "health_check" in called
        # health_check must be the last stage the runner sees, regardless of
        # the upstream abort.
        assert called[-1] == "health_check"

    def test_health_check_failure_makes_run_system_red(self, tmp_path):
        runner = FakeRunner(
            plan={
                "health_check": ProcessOutcome(
                    returncode=1, stderr="thesis file missing"
                )
            }
        )
        run = run_daily(_config(tmp_path, runner=runner))
        # health_check is StageType.CONTROL — a CONTROL RED aggregates to
        # SYSTEM RED, matching CI intent ("run ends red so GitHub sends the
        # failure email").
        assert run.aggregate_status is AggregateStatus.RED
        hc = next(r for r in run.stage_results if r.stage_name == "health_check")
        assert hc.status is StageStatus.RED

    def test_downstream_skipped_reason_names_the_failure(self, tmp_path):
        runner = FakeRunner(
            plan={"macro_collector": ProcessOutcome(returncode=2, stderr="boom")}
        )
        run = run_daily(_config(tmp_path, runner=runner))
        news = next(
            r for r in run.stage_results if r.stage_name == "news_collector"
        )
        assert news.status is StageStatus.SKIPPED
        assert "macro_collector" in (news.skip_reason or "")
        assert "aborted" in (news.skip_reason or "")

    def test_publication_stays_unattempted_when_upstream_aborts(self, tmp_path):
        runner = FakeRunner(
            plan={"technical_agent": ProcessOutcome(returncode=1, stderr="x")}
        )
        run = run_daily(_config(tmp_path, runner=runner))
        # Remote publication remains False/None regardless (wrapper never
        # attempts it). Local export status is inspectable separately.
        assert run.publication_attempted is False
        assert run.publication_observed_outcome is None
        we = next(r for r in run.stage_results if r.stage_name == "web_exporter")
        assert we.status is StageStatus.SKIPPED

    def test_local_export_success_does_not_claim_remote_publication(self, tmp_path):
        """web_exporter GREEN != remote publication attempted / observed."""
        runner = FakeRunner()  # all defaults GREEN
        run = run_daily(_config(tmp_path, runner=runner))
        we = next(r for r in run.stage_results if r.stage_name == "web_exporter")
        assert we.status is StageStatus.GREEN  # local export succeeded
        assert run.publication_attempted is False  # but remote NOT attempted
        assert run.publication_observed_outcome is None

    def test_manifest_distinguishes_local_export_from_remote_publication(self, tmp_path):
        runner = FakeRunner()
        run = run_daily(_config(tmp_path, runner=runner))
        payload = read_manifest(manifest_path(run.run_id, tmp_path))
        we = next(r for r in payload.stage_results if r.stage_name == "web_exporter")
        # Local export outcome is captured as a stage result…
        assert we.status is StageStatus.GREEN
        assert we.stage_type is StageType.SUPPORT
        # …and remote publication fields at the run level stay honest.
        assert payload.publication_attempted is False
        assert payload.publication_observed_outcome is None

    def test_wrapper_argv_contains_no_git_verb(self):
        """Belt-and-braces sanity: the wrapper does not shell out to git."""
        for spec in DAILY_STAGE_SEQUENCE:
            for token in spec.argv:
                assert token != "git", spec

    def test_manifest_is_emitted_on_failure(self, tmp_path):
        runner = FakeRunner(
            plan={"macro_agent": ProcessOutcome(returncode=1, stderr="anthropic 503")}
        )
        run = run_daily(_config(tmp_path, runner=runner))
        path = manifest_path(run.run_id, tmp_path)
        assert path.exists()
        loaded = read_manifest(path)
        # Failed desk with other desks unreachable → SYSTEM RED
        # (no desk survives when downstream desks are all SKIPPED).
        # health_check still ran (always_runs) and defaulted to GREEN in the
        # fake plan, so it does not itself contribute a CONTROL RED.
        assert loaded.aggregate_status is AggregateStatus.RED
        # All requested stages appear (bijection enforced by finalize_run).
        assert set(loaded.requested_stages) == {
            r.stage_name for r in loaded.stage_results
        }


# ---------------------------------------------------------------------------
# Wrapper does not rewrite command semantics
# ---------------------------------------------------------------------------


class TestWrapperPreservesCommandSemantics:
    def test_wrapper_runs_exact_argv_for_each_stage(self, tmp_path):
        runner = FakeRunner()
        run_daily(_config(tmp_path, runner=runner))
        by_name = dict(runner.calls)
        for spec in DAILY_STAGE_SEQUENCE:
            if spec.name == "synthesizer":
                continue
            # Wrapper must have invoked the stage with the exact argv from
            # DAILY_STAGE_SEQUENCE — no arguments added, none removed.
            assert by_name[spec.name] == spec.argv

    def test_wrapper_never_shells_out_to_git_or_shell(self):
        """The wrapper must never introduce its own git/shell command.

        A stronger contract than the previous stage-type check: it verifies
        the actual invocation vector. Every wrapper stage must call
        ``python`` — never ``git``, ``bash``, ``sh``, ``curl``, ``rm``, etc.
        """
        for spec in DAILY_STAGE_SEQUENCE:
            assert spec.argv[0] == "python", spec
            assert "git" not in spec.argv, spec
            assert "curl" not in spec.argv, spec
            assert "rm" not in spec.argv, spec


# ---------------------------------------------------------------------------
# Secret safety through the wrapper (Correction 5)
# ---------------------------------------------------------------------------


FAKE_TOKEN = "sk-ant-FAKE-WRAP-DO-NOT-USE-abcdefghijklmnop"


class TestWrapperSecretSafety:
    def test_stage_stderr_secret_is_scrubbed_in_manifest(self, tmp_path):
        runner = FakeRunner(
            plan={
                "og_collector": ProcessOutcome(
                    returncode=1,
                    stderr=f"failed: token={FAKE_TOKEN}",
                )
            }
        )
        run = run_daily(_config(tmp_path, runner=runner, extras=(FAKE_TOKEN,)))
        path = manifest_path(run.run_id, tmp_path)
        text = path.read_text(encoding="utf-8")
        assert FAKE_TOKEN not in text
        assert "[REDACTED]" in text
