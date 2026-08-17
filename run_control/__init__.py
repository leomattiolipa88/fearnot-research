"""Fear Not — M1 Run Control envelope.

Small, dependency-free control envelope that gives every attempted Fear Not
run a unique identity, typed stage results, deterministic status aggregation
and a machine-readable manifest.

Explicitly out of M1 scope:
  * canonical SQLite persistence (M2)
  * publication gating (M11)
  * canonical local/CI orchestration unification (M10)
  * tracker redesign / desk books
  * research behaviour of any kind
"""

from run_control.aggregation import aggregate_status
from run_control.cli import (
    EXIT_MANIFEST_FAILURE,
    EXIT_OK,
    EXIT_SYSTEM_RED,
    cli_run,
    derive_exit_code,
    has_execution_failure,
)
from run_control.daily_wrapper import (
    DAILY_STAGE_SEQUENCE,
    DailyRunConfig,
    ProcessFailed,
    ProcessOutcome,
    ProcessRunner,
    StageSpec,
    build_default_config,
    default_process_runner,
    run_daily,
    run_daily_and_get_manifest_path,
)
from run_control.git_meta import GitMetadata, capture_git_metadata
from run_control.manifest import (
    RunFinalizationError,
    finalize_run,
    manifest_path,
    read_manifest,
    write_manifest,
)
from run_control.models import (
    AggregateStatus,
    RunRecord,
    StageHint,
    StageResult,
    StageStatus,
    StageType,
    utc_now,
)
from run_control.redaction import redact_secrets
from run_control.run_id import generate_run_id, is_valid_run_id
from run_control.runner import execute_stage, skipped_stage

__all__ = [
    "AggregateStatus",
    "DAILY_STAGE_SEQUENCE",
    "DailyRunConfig",
    "EXIT_MANIFEST_FAILURE",
    "EXIT_OK",
    "EXIT_SYSTEM_RED",
    "GitMetadata",
    "ProcessFailed",
    "ProcessOutcome",
    "ProcessRunner",
    "RunFinalizationError",
    "RunRecord",
    "StageHint",
    "StageResult",
    "StageSpec",
    "StageStatus",
    "StageType",
    "aggregate_status",
    "build_default_config",
    "capture_git_metadata",
    "cli_run",
    "default_process_runner",
    "derive_exit_code",
    "execute_stage",
    "finalize_run",
    "generate_run_id",
    "has_execution_failure",
    "is_valid_run_id",
    "manifest_path",
    "read_manifest",
    "redact_secrets",
    "run_daily",
    "run_daily_and_get_manifest_path",
    "skipped_stage",
    "utc_now",
    "write_manifest",
]
