"""Typed contracts for the M1 control envelope.

Nothing in this module reaches into research code. StageResult / RunRecord
are pure data holders that the runner and manifest layers operate on.
Terminal results are frozen dataclasses; mutable collections are converted
to tuples in ``__post_init__`` so that a validated terminal record cannot
be silently mutated after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Sequence


class StageStatus(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    SKIPPED = "SKIPPED"


class StageType(str, Enum):
    CONTROL = "CONTROL"
    DESK = "DESK"
    SUPPORT = "SUPPORT"
    PUBLICATION = "PUBLICATION"


class AggregateStatus(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


def utc_now() -> datetime:
    """UTC timezone-aware ``now`` — the single time source for the envelope."""
    return datetime.now(timezone.utc)


def _require_utc(field_name: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime (got {type(value).__name__})")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC (got {value!r})")
    offset = value.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{field_name} must be timezone-aware UTC (got {value!r})")


@dataclass(frozen=True)
class StageHint:
    """Advisory return value from a stage callable.

    A callable executed inside ``execute_stage`` may return a StageHint to
    communicate advisory metadata (status, artifact refs, validation notes)
    while leaving all control-owned metadata (name, type, timestamps) to
    the wrapper. This closes the door to callables that would try to
    hijack wrapper-controlled fields by returning a full StageResult.
    """

    status: StageStatus | None = None
    artifact_references: tuple[str, ...] = ()
    data_issue_summary: str | None = None
    validation_summary: str | None = None
    retry_count: int = 0
    safe_error_summary: str | None = None

    def __post_init__(self) -> None:
        if self.status is not None and not isinstance(self.status, StageStatus):
            object.__setattr__(self, "status", StageStatus(self.status))
        if not isinstance(self.artifact_references, tuple):
            object.__setattr__(
                self, "artifact_references", tuple(self.artifact_references)
            )


@dataclass(frozen=True)
class StageResult:
    """Terminal record for a single controlled stage.

    A stage produces exactly one StageResult with one terminal status —
    stages must not silently disappear from a run. Once validated, the
    record is immutable: collections are stored as tuples and the dataclass
    is frozen. Invariants enforced in ``__post_init__``:

      * timestamps are timezone-aware UTC and non-null
      * ended_at >= started_at
      * retry_count >= 0
      * SKIPPED requires a non-empty skip_reason
      * SKIPPED cannot carry safe_error_summary
      * RED cannot carry a skip_reason
      * RED must carry at least one explanatory field
        (safe_error_summary, validation_summary, or data_issue_summary)
      * GREEN cannot carry safe_error_summary
      * YELLOW/GREEN cannot carry skip_reason
    """

    stage_name: str
    stage_type: StageType
    started_at: datetime
    ended_at: datetime
    status: StageStatus
    artifact_references: tuple[str, ...] = ()
    data_issue_summary: str | None = None
    validation_summary: str | None = None
    retry_count: int = 0
    safe_error_summary: str | None = None
    skip_reason: str | None = None

    def __post_init__(self) -> None:
        # Normalize enums first so downstream checks can rely on identity.
        if not isinstance(self.status, StageStatus):
            object.__setattr__(self, "status", StageStatus(self.status))
        if not isinstance(self.stage_type, StageType):
            object.__setattr__(self, "stage_type", StageType(self.stage_type))
        # Freeze mutable inputs.
        if not isinstance(self.artifact_references, tuple):
            object.__setattr__(
                self, "artifact_references", tuple(self.artifact_references)
            )

        if not isinstance(self.stage_name, str) or not self.stage_name.strip():
            raise ValueError("stage_name must be a non-empty string")

        _require_utc("started_at", self.started_at)
        _require_utc("ended_at", self.ended_at)
        if self.ended_at < self.started_at:
            raise ValueError(
                f"StageResult {self.stage_name!r}: ended_at < started_at "
                f"({self.ended_at.isoformat()} < {self.started_at.isoformat()})"
            )

        if not isinstance(self.retry_count, int) or isinstance(
            self.retry_count, bool
        ):
            raise ValueError(
                f"StageResult {self.stage_name!r}: retry_count must be int"
            )
        if self.retry_count < 0:
            raise ValueError(
                f"StageResult {self.stage_name!r}: retry_count cannot be "
                f"negative (got {self.retry_count})"
            )

        if self.status is StageStatus.SKIPPED:
            if not self.skip_reason or not self.skip_reason.strip():
                raise ValueError(
                    f"StageResult {self.stage_name!r}: SKIPPED requires a "
                    f"non-empty skip_reason."
                )
            if self.safe_error_summary:
                raise ValueError(
                    f"StageResult {self.stage_name!r}: SKIPPED cannot carry "
                    f"safe_error_summary — status would mask a failure."
                )

        if self.status is StageStatus.RED:
            if self.skip_reason:
                raise ValueError(
                    f"StageResult {self.stage_name!r}: RED cannot carry a "
                    f"skip_reason — a failure is not a skip."
                )
            explanations = (
                self.safe_error_summary,
                self.validation_summary,
                self.data_issue_summary,
            )
            if not any(e and str(e).strip() for e in explanations):
                raise ValueError(
                    f"StageResult {self.stage_name!r}: RED must carry an "
                    f"explanation (safe_error_summary, validation_summary, "
                    f"or data_issue_summary)."
                )

        if self.status is StageStatus.GREEN:
            if self.safe_error_summary:
                raise ValueError(
                    f"StageResult {self.stage_name!r}: GREEN cannot carry "
                    f"safe_error_summary."
                )
            if self.skip_reason:
                raise ValueError(
                    f"StageResult {self.stage_name!r}: GREEN cannot carry a "
                    f"skip_reason."
                )

        if self.status is StageStatus.YELLOW and self.skip_reason:
            raise ValueError(
                f"StageResult {self.stage_name!r}: YELLOW cannot carry a "
                f"skip_reason."
            )


@dataclass
class RunRecord:
    """Aggregate record for one attempted controlled Fear Not run.

    Mutable during build (stages accumulate incrementally); becomes locked
    at finalization by ``manifest.finalize_run`` before serialization.
    """

    run_id: str
    started_at: datetime
    ended_at: datetime | None
    cadence: str | None
    trigger: str | None
    requested_stages: list[str]
    git_sha: str | None
    git_branch: str | None
    git_dirty: bool | None
    python_version: str | None
    known_model_identifiers: dict[str, str | None] = field(default_factory=dict)
    known_prompt_identifiers: dict[str, str | None] = field(default_factory=dict)
    stage_results: list[StageResult] = field(default_factory=list)
    aggregate_status: AggregateStatus | None = None
    publication_attempted: bool = False
    publication_observed_outcome: str | None = None
    safe_errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.aggregate_status is not None and not isinstance(
            self.aggregate_status, AggregateStatus
        ):
            self.aggregate_status = AggregateStatus(self.aggregate_status)
        _require_utc("started_at", self.started_at)
        if self.ended_at is not None:
            _require_utc("ended_at", self.ended_at)
            if self.ended_at < self.started_at:
                raise ValueError(
                    "RunRecord.ended_at < started_at "
                    f"({self.ended_at.isoformat()} < {self.started_at.isoformat()})"
                )
        # Requested-stage uniqueness at construction time — cheap invariant.
        seen: set[str] = set()
        dupes: list[str] = []
        for name in self.requested_stages:
            if name in seen:
                dupes.append(name)
            seen.add(name)
        if dupes:
            raise ValueError(
                f"RunRecord.requested_stages contains duplicates: "
                f"{sorted(set(dupes))}"
            )
