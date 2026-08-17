"""Safe stage execution wrapper.

``execute_stage`` runs a callable and always produces exactly one terminal
StageResult whose control-owned metadata (stage_name, stage_type,
started_at, ended_at) the callable cannot override. Advisory data from the
callable is accepted only through ``StageStatus`` (bare status) or
``StageHint`` (typed advisory dataclass). Every internal path — including
post-call normalization failures — funnels into a safe RED result rather
than escaping as an unexpected exception.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Iterable

from run_control.models import (
    StageHint,
    StageResult,
    StageStatus,
    StageType,
    utc_now,
)
from run_control.redaction import redact_secrets


def execute_stage(
    stage_name: str,
    stage_type: StageType,
    fn: Callable[[], Any],
    *,
    artifact_references: Iterable[str] | None = None,
    extra_secret_values: Iterable[str] = (),
) -> StageResult:
    """Run ``fn`` under the M1 envelope and return a terminal StageResult.

    Return-value contract for ``fn``:

      * ``None`` → GREEN (no advisory)
      * ``StageStatus.GREEN`` / ``YELLOW`` / ``RED`` → that status
      * ``StageStatus.SKIPPED`` → contract violation → RED
      * ``StageHint(...)`` → advisory fields merged, wrapper still owns
        name/type/timestamps
      * ``StageResult(...)`` → advisory fields only (status/artifact_refs/
        summaries/retry_count) are honored; the returned StageResult's
        stage_name, stage_type, and timestamps are DISCARDED — wrapper
        control state is authoritative.
      * anything else → RED with a contract-violation explanation

    Exceptions raised by ``fn`` become RED with a sanitized error summary.
    Post-call normalization failures also become RED — they never escape.
    """
    baseline_refs = tuple(artifact_references or ())
    extras_tuple = tuple(extra_secret_values)

    started = utc_now()
    try:
        outcome = fn()
    except BaseException as exc:  # noqa: BLE001 — intentional catch-all
        ended = utc_now()
        return _red(
            stage_name,
            stage_type,
            started,
            ended,
            baseline_refs,
            f"{type(exc).__name__}: {exc}",
            extras_tuple,
        )

    ended = utc_now()
    try:
        return _terminal_from_outcome(
            stage_name,
            stage_type,
            started,
            ended,
            outcome,
            baseline_refs,
            extras_tuple,
        )
    except BaseException as normalization_exc:  # noqa: BLE001
        # Post-call normalization / invariant failure must not escape.
        return _red(
            stage_name,
            stage_type,
            started,
            ended,
            baseline_refs,
            f"stage {stage_name!r} post-call contract failure: "
            f"{type(normalization_exc).__name__}: {normalization_exc}",
            extras_tuple,
        )


def _red(
    stage_name: str,
    stage_type: StageType,
    started: datetime,
    ended: datetime,
    baseline_refs: tuple[str, ...],
    raw_error: str,
    extras: tuple[str, ...],
) -> StageResult:
    return StageResult(
        stage_name=stage_name,
        stage_type=stage_type,
        started_at=started,
        ended_at=ended,
        status=StageStatus.RED,
        artifact_references=baseline_refs,
        safe_error_summary=redact_secrets(raw_error, extra_values=extras) or raw_error,
    )


def _terminal_from_outcome(
    stage_name: str,
    stage_type: StageType,
    started: datetime,
    ended: datetime,
    outcome: Any,
    baseline_refs: tuple[str, ...],
    extras: tuple[str, ...],
) -> StageResult:
    # Extract advisory fields depending on outcome type. Wrapper-owned
    # metadata (name, type, timestamps) is NEVER taken from `outcome`.
    if outcome is None:
        status: StageStatus | None = StageStatus.GREEN
        adv_refs: tuple[str, ...] = ()
        data_summary: str | None = None
        validation: str | None = None
        retry: int = 0
        error_summary: str | None = None
    elif isinstance(outcome, StageStatus):
        status = outcome
        adv_refs = ()
        data_summary = validation = error_summary = None
        retry = 0
    elif isinstance(outcome, StageHint):
        status = outcome.status or StageStatus.GREEN
        adv_refs = outcome.artifact_references
        data_summary = outcome.data_issue_summary
        validation = outcome.validation_summary
        retry = outcome.retry_count
        error_summary = outcome.safe_error_summary
    elif isinstance(outcome, StageResult):
        # Advisory fields only. Wrapper discards outcome's name/type/timestamps.
        status = outcome.status
        adv_refs = outcome.artifact_references
        data_summary = outcome.data_issue_summary
        validation = outcome.validation_summary
        retry = outcome.retry_count
        error_summary = outcome.safe_error_summary
    else:
        raise ValueError(
            f"stage {stage_name!r}: callable returned unsupported type "
            f"{type(outcome).__name__} — expected None, StageStatus, "
            f"StageHint, or StageResult"
        )

    if status is StageStatus.SKIPPED:
        # A callable that actually ran cannot legitimately report SKIPPED —
        # SKIPPED is intentional non-execution, and use skipped_stage() for it.
        raise ValueError(
            f"stage {stage_name!r}: callable reported SKIPPED after execution; "
            f"use skipped_stage() for intentional non-execution."
        )

    if retry < 0:
        raise ValueError(
            f"stage {stage_name!r}: retry_count cannot be negative (got {retry})"
        )

    combined_refs = baseline_refs + tuple(adv_refs)

    # If callable claims RED without giving any explanation, synthesize one so
    # StageResult's RED-requires-explanation invariant holds.
    if status is StageStatus.RED and not any(
        v and str(v).strip() for v in (error_summary, validation, data_summary)
    ):
        error_summary = f"stage {stage_name!r} returned RED without explanation"

    # A callable-supplied error_summary passes through the redactor too, in
    # case the callable set it verbatim from user-facing exception text.
    if error_summary:
        error_summary = redact_secrets(error_summary, extra_values=extras)

    # GREEN carrying an error summary would be a lie; either the status is
    # wrong or the summary is wrong — refuse to serialize either way.
    if status is StageStatus.GREEN and error_summary:
        raise ValueError(
            f"stage {stage_name!r}: GREEN cannot carry safe_error_summary"
        )

    return StageResult(
        stage_name=stage_name,
        stage_type=stage_type,
        started_at=started,
        ended_at=ended,
        status=status,
        artifact_references=combined_refs,
        data_issue_summary=data_summary,
        validation_summary=validation,
        retry_count=retry,
        safe_error_summary=error_summary,
    )


def skipped_stage(
    stage_name: str,
    stage_type: StageType,
    skip_reason: str,
) -> StageResult:
    """Return a SKIPPED StageResult for an intentionally non-executed stage.

    Requiring a non-empty ``skip_reason`` keeps the "no hiding failure
    behind SKIPPED" invariant honest: a bare skip must justify itself.
    """
    if not isinstance(skip_reason, str) or not skip_reason.strip():
        raise ValueError("skipped_stage requires a non-empty skip_reason")
    now = utc_now()
    return StageResult(
        stage_name=stage_name,
        stage_type=stage_type,
        started_at=now,
        ended_at=now,
        status=StageStatus.SKIPPED,
        skip_reason=skip_reason.strip(),
    )
