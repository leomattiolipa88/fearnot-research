"""Opt-in M1 controlled wrapper around ONE existing Fear Not daily path.

Scope statement:

  * This wrapper is NOT the M10 canonical runner.
  * It is NOT wired into GitHub Actions.
  * It does NOT replace ``update_web.sh``.
  * It does NOT modify existing workflows or entry points.
  * It runs the existing stages as CHILD PROCESSES in the exact order they
    already run in ``.github/workflows/daily_pipeline.yml``. Nothing is
    reordered, no arguments are changed, no research behavior is altered.

What the wrapper adds:

  * a run_id created BEFORE the first stage begins
  * run metadata (git, python, models, cadence, trigger)
  * exactly one terminal StageResult for every requested stage
    (downstream stages become SKIPPED with a clear upstream-abort reason)
  * an aggregate process status
  * a final non-authoritative JSON manifest at
    ``logs/runs/<run_id>/manifest.json``

The wrapper performs NO git mutations, NO SQLite writes, and NO research.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol, Sequence

from run_control.aggregation import aggregate_status
from run_control.git_meta import capture_git_metadata
from run_control.manifest import manifest_path, write_manifest
from run_control.models import (
    AggregateStatus,
    RunRecord,
    StageResult,
    StageStatus,
    StageType,
    utc_now,
)
from run_control.runner import execute_stage, skipped_stage
from run_control.run_id import generate_run_id

# ---------------------------------------------------------------------------
# Stage specification
#
# Exact stage sequence transcribed from `.github/workflows/daily_pipeline.yml`.
# The workflow has TWO abort regimes:
#   * Stages 1-12 run inside a single `run: |` shell block. GitHub Actions
#     uses `bash -eo pipefail` for `run:` steps, so the first non-zero exit
#     aborts the block. `set -e` inside `update_web.sh` has the same effect
#     locally.
#   * `health_check.py` runs in its own step with `if: always()`, so it
#     fires regardless of upstream success or failure — the CI comment
#     explicitly documents this ("last step, on purpose"). Health-check
#     failure ends the run RED so the failure email fires.
#
# The wrapper reproduces both regimes: sequential abort for stages 1-12,
# then always_runs=True for health_check. Do not reorder. Any change to
# the underlying workflow must be reflected here; the sequence is asserted
# by ``test_run_control_daily_wrapper.py::test_stage_order_matches_daily_pipeline``.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageSpec:
    name: str
    stage_type: StageType
    argv: tuple[str, ...]
    monday_only: bool = False
    always_runs: bool = False  # mirrors GitHub Actions `if: always()`


DAILY_STAGE_SEQUENCE: tuple[StageSpec, ...] = (
    StageSpec("macro_collector", StageType.SUPPORT, ("python", "collector.py")),
    StageSpec("news_collector", StageType.SUPPORT, ("python", "news_collector.py")),
    StageSpec("og_collector", StageType.SUPPORT, ("python", "og_collector.py")),
    StageSpec(
        "og_news_collector", StageType.SUPPORT, ("python", "og_news_collector.py")
    ),
    StageSpec(
        "technical_collector",
        StageType.SUPPORT,
        ("python", "technical_collector.py"),
    ),
    StageSpec(
        "options_flow_collector",
        StageType.SUPPORT,
        ("python", "options_flow_collector.py"),
    ),
    StageSpec("macro_agent", StageType.DESK, ("python", "agent.py")),
    StageSpec("technical_agent", StageType.DESK, ("python", "technical_agent.py")),
    StageSpec("og_agent", StageType.DESK, ("python", "og_agent.py")),
    StageSpec(
        "synthesizer",
        StageType.DESK,
        ("python", "synthesizer.py"),
        monday_only=True,
    ),
    StageSpec(
        "tracker_evaluate",
        StageType.SUPPORT,
        (
            "python",
            "-c",
            "from tracker import evaluar_convicciones_vencidas; "
            "evaluar_convicciones_vencidas()",
        ),
    ),
    # web_exporter.py only *generates* data/web_data.json locally. The real
    # CI performs a separate "Checkout fearnot-web" + "Update fearnot-web"
    # (git commit + push) step that this wrapper deliberately does NOT
    # replicate — the M1 wrapper performs no git mutations (spec §17).
    # Therefore this stage is SUPPORT (local export generation), NOT
    # PUBLICATION. Successful export DOES NOT imply remote delivery.
    StageSpec("web_exporter", StageType.SUPPORT, ("python", "web_exporter.py")),
    # health_check runs `if: always()` in the workflow — intentionally
    # positioned AFTER web_exporter and AFTER the CI-only git push step.
    # Failure → SYSTEM RED so the operator/CI knows the run is unhealthy
    # even though the healthy portion has already been published (M11 will
    # revisit this ordering; M1 only observes it).
    StageSpec(
        "health_check",
        StageType.CONTROL,
        ("python", "health_check.py"),
        always_runs=True,
    ),
)


# ---------------------------------------------------------------------------
# Injectable process runner
# ---------------------------------------------------------------------------


@dataclass
class ProcessOutcome:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class ProcessRunner(Protocol):
    def __call__(
        self, stage_name: str, argv: Sequence[str]
    ) -> ProcessOutcome:  # pragma: no cover - protocol
        ...


def default_process_runner(
    stage_name: str, argv: Sequence[str], *, cwd: Path | None = None
) -> ProcessOutcome:
    """Real runner — invokes the existing script via ``subprocess.run``.

    Never used by automated tests; tests always supply a FakeProcessRunner.
    """
    proc = subprocess.run(
        list(argv),
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
    )
    return ProcessOutcome(
        returncode=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )


class ProcessFailed(RuntimeError):
    """Raised by the per-stage callable when the child process fails."""

    def __init__(self, stage_name: str, outcome: ProcessOutcome) -> None:
        tail = (outcome.stderr or outcome.stdout or "").strip()
        if len(tail) > 500:
            tail = "…" + tail[-500:]
        parts = [
            f"stage {stage_name!r} exited with returncode {outcome.returncode}"
        ]
        if tail:
            parts.append(f"stderr(tail): {tail}")
        super().__init__("; ".join(parts))


# ---------------------------------------------------------------------------
# Wrapper entry point
# ---------------------------------------------------------------------------


@dataclass
class DailyRunConfig:
    """Bounded configuration for a controlled daily run.

    Values default to conservative choices so the wrapper can be exercised
    from tests with fake stages and, separately, from an operator terminal
    (opt-in — not wired into CI).
    """

    repo_root: Path
    logs_dir: Path
    is_monday: bool
    trigger: str = "manual"
    known_model_identifiers: dict[str, str | None] = field(default_factory=dict)
    known_prompt_identifiers: dict[str, str | None] = field(default_factory=dict)
    extra_secret_values: tuple[str, ...] = ()
    now: datetime | None = None
    process_runner: ProcessRunner | None = None
    stage_specs: tuple[StageSpec, ...] = DAILY_STAGE_SEQUENCE


def _stage_callable(
    runner: ProcessRunner, spec: StageSpec
) -> Callable[[], StageStatus]:
    def _run_it() -> StageStatus:
        outcome = runner(spec.name, spec.argv)
        if outcome.returncode != 0:
            raise ProcessFailed(spec.name, outcome)
        return StageStatus.GREEN

    return _run_it


def run_daily(config: DailyRunConfig) -> RunRecord:
    """Run the daily pipeline stage sequence under the M1 envelope."""
    runner = config.process_runner or (
        lambda name, argv: default_process_runner(
            name, argv, cwd=config.repo_root
        )
    )

    run_id = generate_run_id(now=config.now)  # BEFORE any stage begins
    started = utc_now()

    git = capture_git_metadata(config.repo_root)
    py_version = platform.python_version()

    stage_specs = tuple(config.stage_specs)
    requested_stages = [s.name for s in stage_specs]

    results: list[StageResult] = []
    aborted = False
    aborting_stage: str | None = None

    for spec in stage_specs:
        if spec.monday_only and not config.is_monday:
            results.append(
                skipped_stage(
                    spec.name,
                    spec.stage_type,
                    "Monday-only stage; today is not Monday",
                )
            )
            continue
        if aborted and not spec.always_runs:
            results.append(
                skipped_stage(
                    spec.name,
                    spec.stage_type,
                    f"upstream stage '{aborting_stage}' failed; "
                    f"pipeline aborted before this stage could run",
                )
            )
            continue

        result = execute_stage(
            spec.name,
            spec.stage_type,
            _stage_callable(runner, spec),
            extra_secret_values=config.extra_secret_values,
        )
        results.append(result)
        # Only sequential-abort stages cascade an abort. An always_runs
        # stage's failure is real (it becomes RED and drives aggregation)
        # but it does not prevent any *further* always_runs stages from
        # firing — that mirrors GitHub Actions `if: always()` semantics.
        if result.status is StageStatus.RED and not spec.always_runs:
            aborted = True
            aborting_stage = spec.name

    ended = utc_now()

    # M1 publication honesty:
    # The daily wrapper does NOT attempt remote publication. web_exporter.py
    # only generates data/web_data.json locally; the real Vercel-visible
    # publication happens in a separate GitHub-Actions git-push step that
    # the wrapper does not replicate (spec §17: no git mutations).
    # Therefore remote publication is not attempted and not observed here.
    # The LOCAL export status is inspectable via stage_results[name="web_exporter"].
    publication_attempted = False
    publication_observed_outcome = None

    run = RunRecord(
        run_id=run_id,
        started_at=started,
        ended_at=ended,
        cadence="daily",
        trigger=config.trigger,
        requested_stages=requested_stages,
        git_sha=git.sha,
        git_branch=git.branch,
        git_dirty=git.dirty,
        python_version=py_version,
        known_model_identifiers=dict(config.known_model_identifiers),
        known_prompt_identifiers=dict(config.known_prompt_identifiers),
        stage_results=results,
        aggregate_status=aggregate_status(results),
        publication_attempted=publication_attempted,
        publication_observed_outcome=publication_observed_outcome,
        safe_errors=[
            r.safe_error_summary
            for r in results
            if r.safe_error_summary
        ],
    )

    path = manifest_path(run_id, config.logs_dir)
    write_manifest(run, path, extra_secret_values=config.extra_secret_values)
    return run


def run_daily_and_get_manifest_path(config: DailyRunConfig) -> Path:
    """Convenience: run and return the manifest path (for scripts)."""
    run = run_daily(config)
    return manifest_path(run.run_id, config.logs_dir)


# ---------------------------------------------------------------------------
# Convenience for local operator use — opt-in only, never auto-invoked
# ---------------------------------------------------------------------------


def build_default_config(
    repo_root: Path | str,
    *,
    is_monday: bool | None = None,
    trigger: str = "manual",
    logs_dir: Path | str | None = None,
) -> DailyRunConfig:
    """Assemble a plausible default config from the repository layout."""
    root = Path(repo_root).resolve()
    logs = Path(logs_dir).resolve() if logs_dir else root / "logs"
    if is_monday is None:
        is_monday = utc_now().weekday() == 0  # Monday == 0 in Python

    # Import config.MODEL lazily so importing this module never triggers a
    # research-file side effect. If config isn't importable in the caller's
    # environment we still return a valid config with unknown identifiers.
    known_models: dict[str, str | None] = {}
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        import config as _cfg  # type: ignore[import-not-found]

        model_name = getattr(_cfg, "MODEL", None)
        for desk in (
            "macro_agent",
            "technical_agent",
            "og_agent",
            "synthesizer",
        ):
            known_models[desk] = model_name
    except Exception:  # noqa: BLE001 — capture is honest-null on any failure
        known_models = {
            "macro_agent": None,
            "technical_agent": None,
            "og_agent": None,
            "synthesizer": None,
        }

    return DailyRunConfig(
        repo_root=root,
        logs_dir=logs,
        is_monday=is_monday,
        trigger=trigger,
        known_model_identifiers=known_models,
        known_prompt_identifiers={
            "macro_prompt": None,
            "technical_prompt": None,
            "og_prompt": None,
            "synthesizer_prompt": None,
        },
    )
