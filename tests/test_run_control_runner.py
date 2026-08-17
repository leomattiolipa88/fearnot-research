"""Runner + redaction tests.

Covers Codex Correction 2 (execute_stage contract hardening) and
Correction 5 (redaction bypasses), including that fake secrets never
survive the runner-to-manifest boundary.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from run_control import (
    StageHint,
    StageResult,
    StageStatus,
    StageType,
    execute_stage,
    redact_secrets,
    skipped_stage,
    utc_now,
)


# ── E. Exceptions become RED StageResults with a safe error summary ───────────


class TestExceptionsBecomeRed:
    def test_raised_exception_produces_red(self):
        def boom():
            raise ValueError("expected banking input unavailable")

        result = execute_stage("banking", StageType.DESK, boom)
        assert result.status is StageStatus.RED
        assert result.safe_error_summary is not None
        assert "ValueError" in result.safe_error_summary
        assert "banking input unavailable" in result.safe_error_summary
        assert result.stage_name == "banking"
        assert result.stage_type is StageType.DESK

    def test_success_produces_green(self):
        result = execute_stage("macro", StageType.DESK, lambda: None)
        assert result.status is StageStatus.GREEN
        assert result.safe_error_summary is None

    def test_returned_status_is_respected(self):
        result = execute_stage(
            "macro", StageType.DESK, lambda: StageStatus.YELLOW
        )
        assert result.status is StageStatus.YELLOW

    def test_stage_hint_is_respected_but_control_owned(self):
        def hint():
            return StageHint(
                status=StageStatus.YELLOW,
                data_issue_summary="one stale series",
                validation_summary="9/10 validators passed",
                artifact_references=("data/x.json",),
            )

        result = execute_stage("macro", StageType.DESK, hint)
        assert result.status is StageStatus.YELLOW
        assert result.data_issue_summary == "one stale series"
        assert result.validation_summary == "9/10 validators passed"
        assert "data/x.json" in result.artifact_references
        # Wrapper owns identity + timestamps.
        assert result.stage_name == "macro"
        assert result.stage_type is StageType.DESK
        assert result.started_at is not None
        assert result.ended_at is not None

    def test_returned_stage_result_cannot_override_stage_name_or_type(self):
        """Advisory fields kept; control state (name/type/timestamps) not."""
        now = utc_now()

        def hijack():
            return StageResult(
                stage_name="HIJACKED",
                stage_type=StageType.CONTROL,
                started_at=now,
                ended_at=now,
                status=StageStatus.YELLOW,
                data_issue_summary="advisory keeps",
            )

        result = execute_stage("macro", StageType.DESK, hijack)
        assert result.stage_name == "macro"  # not "HIJACKED"
        assert result.stage_type is StageType.DESK  # not CONTROL
        assert result.status is StageStatus.YELLOW  # advisory honored
        assert result.data_issue_summary == "advisory keeps"

    def test_returned_stage_result_cannot_inject_timestamps(self):
        past = utc_now().replace(year=2000)
        future = utc_now().replace(year=2200)

        def spoof():
            return StageResult(
                stage_name="spoof",
                stage_type=StageType.DESK,
                started_at=past,
                ended_at=future,
                status=StageStatus.GREEN,
            )

        result = execute_stage("macro", StageType.DESK, spoof)
        # Wrapper timestamps are authoritative — they bracket the current run.
        assert result.started_at.year >= 2020
        assert result.ended_at.year >= 2020
        assert result.started_at.year < 2100
        assert result.ended_at.year < 2100

    def test_callable_returning_skipped_status_becomes_red(self):
        result = execute_stage(
            "macro", StageType.DESK, lambda: StageStatus.SKIPPED
        )
        assert result.status is StageStatus.RED
        assert "SKIPPED" in (result.safe_error_summary or "")

    def test_callable_returning_skipped_via_stage_hint_becomes_red(self):
        def hint():
            return StageHint(status=StageStatus.SKIPPED)

        result = execute_stage("macro", StageType.DESK, hint)
        assert result.status is StageStatus.RED
        assert "SKIPPED" in (result.safe_error_summary or "")

    def test_callable_returning_stage_result_with_skipped_becomes_red(self):
        now = utc_now()

        def attempt():
            return StageResult(
                stage_name="x",
                stage_type=StageType.DESK,
                started_at=now,
                ended_at=now,
                status=StageStatus.SKIPPED,
                skip_reason="pretending",
            )

        result = execute_stage("macro", StageType.DESK, attempt)
        assert result.status is StageStatus.RED
        assert "SKIPPED" in (result.safe_error_summary or "")

    def test_callable_returning_negative_retry_becomes_red(self):
        result = execute_stage(
            "macro",
            StageType.DESK,
            lambda: StageHint(retry_count=-1),
        )
        assert result.status is StageStatus.RED
        assert "retry_count" in (result.safe_error_summary or "")

    def test_callable_returning_red_without_explanation_gets_synthesized_one(self):
        result = execute_stage(
            "macro", StageType.DESK, lambda: StageStatus.RED
        )
        assert result.status is StageStatus.RED
        assert result.safe_error_summary is not None
        assert len(result.safe_error_summary) > 0

    def test_callable_returning_unsupported_type_becomes_red(self):
        result = execute_stage("macro", StageType.DESK, lambda: 42)
        assert result.status is StageStatus.RED
        assert "unsupported" in (result.safe_error_summary or "").lower()

    def test_execute_stage_never_raises_on_post_call_contract_failure(self):
        # A callable returning something that would violate a StageResult
        # invariant must produce RED, not escape as an exception.
        def bad_hint():
            return StageHint(
                status=StageStatus.GREEN, safe_error_summary="lie"
            )

        result = execute_stage("macro", StageType.DESK, bad_hint)
        assert result.status is StageStatus.RED
        assert "GREEN cannot carry safe_error_summary" in (
            result.safe_error_summary or ""
        )

    def test_failure_is_not_swallowed_or_reclassified(self):
        def boom():
            raise RuntimeError("outage")

        result = execute_stage("web", StageType.PUBLICATION, boom)
        assert result.status is StageStatus.RED
        assert result.status not in (
            StageStatus.GREEN,
            StageStatus.YELLOW,
            StageStatus.SKIPPED,
        )

    def test_skipped_stage_requires_reason(self):
        with pytest.raises(ValueError):
            skipped_stage("synthesizer", StageType.DESK, "")
        with pytest.raises(ValueError):
            skipped_stage("synthesizer", StageType.DESK, "   ")

    def test_skipped_stage_returns_skipped(self):
        result = skipped_stage("synthesizer", StageType.DESK, "not Monday")
        assert result.status is StageStatus.SKIPPED
        assert result.skip_reason == "not Monday"


# ── F. Secret safety in error records ─────────────────────────────────────────


FAKE_ANTHROPIC = "sk-ant-FAKE-TOKEN-DO-NOT-USE-abcdefghijklmnopqrstuvwxyz"
FAKE_BEARER = "Bearer FAKE-abcdefghijklmnopqrstuvwxyz1234567890"
FAKE_BASIC = "Basic ZmFrZS11c2VyOmZha2UtcGFzc3dvcmQK"
FAKE_ENV_VALUE = "fake-fred-key-abcdefghij"
FAKE_GHP = "ghp_FakeAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
FAKE_AIZA = "AIzaFAKEAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


class TestRedaction:
    def test_hides_known_shape_tokens(self):
        text = (
            f"Auth failed: {FAKE_ANTHROPIC} / {FAKE_BEARER} / "
            f"{FAKE_GHP} / {FAKE_AIZA}"
        )
        cleaned = redact_secrets(text)
        for secret in (FAKE_ANTHROPIC, FAKE_GHP, FAKE_AIZA):
            assert secret not in cleaned
        # Bearer sub-string may keep the "Bearer " prefix but not the token.
        assert "FAKE-abcdefghij" not in cleaned
        assert "[REDACTED]" in cleaned

    def test_hides_authorization_bearer_header(self):
        text = f"Authorization: Bearer {FAKE_ENV_VALUE}xyz9876543210 boom"
        cleaned = redact_secrets(text)
        assert FAKE_ENV_VALUE + "xyz" not in cleaned
        assert "Authorization: [REDACTED]" in cleaned

    def test_hides_authorization_basic_header(self):
        text = f"Authorization: {FAKE_BASIC} — boom"
        cleaned = redact_secrets(text)
        assert FAKE_BASIC not in cleaned
        assert "ZmFrZS11c2VyOmZha2UtcGFzc3dvcmQK" not in cleaned
        assert "Authorization: [REDACTED]" in cleaned

    def test_hides_env_style_kv_unquoted(self):
        text = f"crashed with API_KEY={FAKE_ANTHROPIC} at boot"
        cleaned = redact_secrets(text)
        assert FAKE_ANTHROPIC not in cleaned
        assert "API_KEY=[REDACTED]" in cleaned

    def test_hides_env_style_kv_double_quoted(self):
        text = f'crashed with API_KEY="{FAKE_ENV_VALUE}" at boot'
        cleaned = redact_secrets(
            text, extra_values=[FAKE_ENV_VALUE]
        )
        assert FAKE_ENV_VALUE not in cleaned
        assert 'API_KEY="[REDACTED]"' in cleaned

    def test_hides_env_style_kv_single_quoted(self):
        text = f"crashed with SECRET_KEY='{FAKE_ENV_VALUE}' at boot"
        cleaned = redact_secrets(
            text, extra_values=[FAKE_ENV_VALUE]
        )
        assert FAKE_ENV_VALUE not in cleaned
        assert "SECRET_KEY='[REDACTED]'" in cleaned

    def test_extra_values_are_redacted(self):
        text = f"crashed with our config value {FAKE_ENV_VALUE}"
        cleaned = redact_secrets(text, extra_values=[FAKE_ENV_VALUE])
        assert FAKE_ENV_VALUE not in cleaned
        assert "[REDACTED]" in cleaned

    def test_env_var_values_are_redacted_when_key_is_sensitive(
        self, monkeypatch
    ):
        monkeypatch.setenv("MY_FAKE_API_KEY", FAKE_ENV_VALUE)
        text = f"boom {FAKE_ENV_VALUE} while reading env"
        cleaned = redact_secrets(text)
        assert FAKE_ENV_VALUE not in cleaned

    def test_execute_stage_scrubs_exception_message(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY_FAKE", FAKE_ANTHROPIC)

        def boom():
            raise RuntimeError(
                f"Bearer failed: token={FAKE_ANTHROPIC} header={FAKE_BEARER} "
                f"basic={FAKE_BASIC} ghp={FAKE_GHP} aiza={FAKE_AIZA} "
                f'env=SECRET_KEY="{FAKE_ENV_VALUE}"'
            )

        result = execute_stage(
            "macro",
            StageType.DESK,
            boom,
            extra_secret_values=[
                FAKE_ANTHROPIC,
                FAKE_BEARER,
                FAKE_BASIC,
                FAKE_ENV_VALUE,
                FAKE_GHP,
                FAKE_AIZA,
            ],
        )
        assert result.status is StageStatus.RED
        summary = result.safe_error_summary or ""
        for secret in (
            FAKE_ANTHROPIC,
            FAKE_BASIC,
            FAKE_ENV_VALUE,
            FAKE_GHP,
            FAKE_AIZA,
        ):
            assert secret not in summary
