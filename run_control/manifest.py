"""Manifest serialization and finalization.

The manifest is a NON-AUTHORITATIVE operational artifact. It is not
canonical research state; the SQLite database remains the source of truth
for research outputs. Manifests default to ``logs/runs/<run_id>/manifest.json``,
which is already covered by the repository's ``logs/`` ``.gitignore`` rule.

Hardening on top of plain JSON:

  * ``finalize_run`` enforces a bijection between requested stages and
    stage results before a final manifest is emitted.
  * ``write_manifest`` finalizes first, then redacts every operational
    error-bearing field defensively before flushing to disk — so a
    ``safe_error_summary`` set outside of ``execute_stage`` is still
    sanitized before it can be persisted.
  * ``read_manifest`` requires the exact ``schema_version`` and rejects
    timezone-naive timestamps.
  * ``manifest_path`` refuses invalid run IDs and refuses any target that
    would escape its base directory.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from run_control.models import (
    AggregateStatus,
    RunRecord,
    StageResult,
    StageStatus,
    StageType,
)
from run_control.redaction import redact_secrets
from run_control.run_id import is_valid_run_id

_MANIFEST_SCHEMA_VERSION = 1

# Strict field allow-lists for schema_version=1. Unknown fields on read are
# rejected explicitly (Correction C, pass 2): silently ignoring them would
# let a read → write cycle discard data. Future schema versions get their
# own allow-lists; forward-compatible field migration is out of M1 scope.
_ALLOWED_TOP_LEVEL_FIELDS = frozenset(
    {
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
)

_ALLOWED_STAGE_FIELDS = frozenset(
    {
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
    }
)


class RunFinalizationError(ValueError):
    """Raised when a RunRecord fails bijection/finalization checks."""


def _ts_to_str(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _ts_from_str(value: str | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as e:
        raise ValueError(f"manifest {field_name}: cannot parse timestamp {value!r}: {e}")
    if parsed.tzinfo is None:
        raise ValueError(
            f"manifest {field_name}: timestamp {value!r} is timezone-naive; "
            f"refusing silent UTC reinterpretation."
        )
    return parsed.astimezone(timezone.utc)


def _stage_to_dict(stage: StageResult) -> dict[str, Any]:
    return {
        "stage_name": stage.stage_name,
        "stage_type": stage.stage_type.value,
        "started_at": _ts_to_str(stage.started_at),
        "ended_at": _ts_to_str(stage.ended_at),
        "status": stage.status.value,
        "artifact_references": list(stage.artifact_references),
        "data_issue_summary": stage.data_issue_summary,
        "validation_summary": stage.validation_summary,
        "retry_count": stage.retry_count,
        "safe_error_summary": stage.safe_error_summary,
        "skip_reason": stage.skip_reason,
    }


def _stage_from_dict(data: dict[str, Any]) -> StageResult:
    unknown = set(data.keys()) - _ALLOWED_STAGE_FIELDS
    if unknown:
        raise ValueError(
            f"stage_result contains unknown fields for schema_version="
            f"{_MANIFEST_SCHEMA_VERSION}: {sorted(unknown)}"
        )
    return StageResult(
        stage_name=data["stage_name"],
        stage_type=StageType(data["stage_type"]),
        started_at=_ts_from_str(data.get("started_at"), field_name="stage started_at"),
        ended_at=_ts_from_str(data.get("ended_at"), field_name="stage ended_at"),
        status=StageStatus(data["status"]),
        artifact_references=tuple(data.get("artifact_references") or ()),
        data_issue_summary=data.get("data_issue_summary"),
        validation_summary=data.get("validation_summary"),
        retry_count=int(data.get("retry_count") or 0),
        safe_error_summary=data.get("safe_error_summary"),
        skip_reason=data.get("skip_reason"),
    )


def run_to_dict(run: RunRecord) -> dict[str, Any]:
    return {
        "schema_version": _MANIFEST_SCHEMA_VERSION,
        "run_id": run.run_id,
        "started_at": _ts_to_str(run.started_at),
        "ended_at": _ts_to_str(run.ended_at),
        "cadence": run.cadence,
        "trigger": run.trigger,
        "requested_stages": list(run.requested_stages),
        "git_sha": run.git_sha,
        "git_branch": run.git_branch,
        "git_dirty": run.git_dirty,
        "python_version": run.python_version,
        "known_model_identifiers": dict(run.known_model_identifiers),
        "known_prompt_identifiers": dict(run.known_prompt_identifiers),
        "stage_results": [_stage_to_dict(s) for s in run.stage_results],
        "aggregate_status": (
            run.aggregate_status.value if run.aggregate_status is not None else None
        ),
        "publication_attempted": bool(run.publication_attempted),
        "publication_observed_outcome": run.publication_observed_outcome,
        "safe_errors": list(run.safe_errors),
    }


def run_from_dict(data: dict[str, Any]) -> RunRecord:
    if "schema_version" not in data:
        raise ValueError("manifest missing required field: schema_version")
    schema = data["schema_version"]
    if schema != _MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported manifest schema_version={schema!r} "
            f"(this build supports {_MANIFEST_SCHEMA_VERSION})"
        )
    unknown = set(data.keys()) - _ALLOWED_TOP_LEVEL_FIELDS
    if unknown:
        raise ValueError(
            f"manifest contains unknown top-level fields for schema_version="
            f"{_MANIFEST_SCHEMA_VERSION}: {sorted(unknown)}"
        )
    if "run_id" not in data:
        raise ValueError("manifest missing required field: run_id")
    if not is_valid_run_id(data["run_id"]):
        raise ValueError(f"manifest run_id is invalid: {data['run_id']!r}")
    agg_raw = data.get("aggregate_status")
    return RunRecord(
        run_id=data["run_id"],
        started_at=_ts_from_str(data["started_at"], field_name="started_at"),
        ended_at=_ts_from_str(data.get("ended_at"), field_name="ended_at"),
        cadence=data.get("cadence"),
        trigger=data.get("trigger"),
        requested_stages=list(data.get("requested_stages") or []),
        git_sha=data.get("git_sha"),
        git_branch=data.get("git_branch"),
        git_dirty=data.get("git_dirty"),
        python_version=data.get("python_version"),
        known_model_identifiers=dict(data.get("known_model_identifiers") or {}),
        known_prompt_identifiers=dict(data.get("known_prompt_identifiers") or {}),
        stage_results=[_stage_from_dict(s) for s in data.get("stage_results") or []],
        aggregate_status=(AggregateStatus(agg_raw) if agg_raw is not None else None),
        publication_attempted=bool(data.get("publication_attempted") or False),
        publication_observed_outcome=data.get("publication_observed_outcome"),
        safe_errors=list(data.get("safe_errors") or []),
    )


def manifest_path(run_id: str, base_dir: Path | str) -> Path:
    """Return the conventional manifest path under ``base_dir/runs/<run_id>``.

    Refuses invalid ``run_id`` values (blocks path-traversal via crafted IDs)
    and defensively asserts the resulting path is under ``base_dir``.
    """
    if not is_valid_run_id(run_id):
        raise ValueError(f"manifest_path: invalid run_id {run_id!r}")
    base = Path(base_dir).resolve()
    candidate = (base / "runs" / run_id / "manifest.json").resolve()
    try:
        candidate.relative_to(base)
    except ValueError as e:
        raise ValueError(
            f"manifest_path: {candidate} escapes base_dir {base}: {e}"
        )
    return candidate


def finalize_run(run: RunRecord) -> None:
    """Verify bijection between requested_stages and stage_results.

    Raises ``RunFinalizationError`` on any violation. Called by
    ``write_manifest`` before serialization so a malformed run never
    produces a misleading successful manifest.
    """
    requested = list(run.requested_stages)
    requested_set = set(requested)
    if len(requested_set) != len(requested):
        dupes = sorted({n for n in requested if requested.count(n) > 1})
        raise RunFinalizationError(
            f"requested_stages contains duplicates: {dupes}"
        )
    result_names = [r.stage_name for r in run.stage_results]
    result_set = set(result_names)
    if len(result_set) != len(result_names):
        dupes = sorted({n for n in result_names if result_names.count(n) > 1})
        raise RunFinalizationError(f"stage_results contains duplicates: {dupes}")
    missing = requested_set - result_set
    if missing:
        raise RunFinalizationError(
            f"missing terminal results for requested stages: {sorted(missing)}"
        )
    unknown = result_set - requested_set
    if unknown:
        raise RunFinalizationError(
            f"unknown stage results not in requested_stages: {sorted(unknown)}"
        )
    if run.aggregate_status is None:
        raise RunFinalizationError(
            "aggregate_status must be set before manifest serialization"
        )


def _sanitize_manifest_dict(
    payload: dict[str, Any], extra_values: Iterable[str] = ()
) -> None:
    """Defensively redact every operational error-bearing string in place.

    Runs regardless of whether execute_stage was used — this is the final
    boundary before bytes hit disk.
    """
    extras = tuple(extra_values)

    top_errors = payload.get("safe_errors") or []
    payload["safe_errors"] = [
        redact_secrets(str(e), extra_values=extras) for e in top_errors
    ]

    for stage_dict in payload.get("stage_results") or []:
        for field_name in (
            "safe_error_summary",
            "data_issue_summary",
            "validation_summary",
        ):
            value = stage_dict.get(field_name)
            if value:
                stage_dict[field_name] = redact_secrets(
                    str(value), extra_values=extras
                )


def write_manifest(
    run: RunRecord,
    path: Path | str,
    *,
    extra_secret_values: Iterable[str] = (),
) -> Path:
    """Serialize ``run`` to ``path``.

    Sequence:
      1. ``finalize_run(run)`` — bijection between requested and results.
      2. serialize to dict, then sanitize every error-bearing string field.
      3. atomic-ish write (parent dirs created; overwrite allowed).
    """
    finalize_run(run)
    payload = run_to_dict(run)
    _sanitize_manifest_dict(payload, extra_values=extra_secret_values)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return p


def read_manifest(path: Path | str) -> RunRecord:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return run_from_dict(data)
