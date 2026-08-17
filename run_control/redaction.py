"""Focused redaction for operational error records.

Scope: prevent obviously-sensitive material (API keys, bearer/basic tokens,
authorization headers, ``KEY=VALUE`` lines for known-sensitive keys,
including quoted forms) from ending up in manifests or safe-error summaries.

Non-goals: this is NOT a cybersecurity framework. It is a defensive filter
sized to the M1 threat model — an operator reading a manifest, an audit log
being pasted into a review — not an adversary with full log access.
"""

from __future__ import annotations

import os
import re
from typing import Iterable

_REDACTED = "[REDACTED]"

# Names that, when they appear as environment variables or as the LHS of
# ``KEY=VALUE`` lines, should have their value redacted.
_SENSITIVE_KEY_TOKENS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "passwd",
    "authorization",
    "auth",
    "credential",
    "private_key",
    "pat",
    "session",
)

# Value patterns that look like secrets on their own (regardless of key name).
# Order matters: the more specific Authorization forms come first so we can
# emit "Authorization: [REDACTED]" rather than a bare "[REDACTED]" that
# leaves the "Authorization:" prefix visible.
_VALUE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"Authorization:\s*(?:Bearer|Basic|Digest)\s+\S+", re.IGNORECASE),
        f"Authorization: {_REDACTED}",
    ),
    (
        re.compile(r"Authorization:\s*\S+", re.IGNORECASE),
        f"Authorization: {_REDACTED}",
    ),
    (
        re.compile(r"Bearer\s+[A-Za-z0-9_\-\.=]{10,}", re.IGNORECASE),
        f"Bearer {_REDACTED}",
    ),
    (
        re.compile(r"Basic\s+[A-Za-z0-9+/=_\-\.]{10,}"),
        f"Basic {_REDACTED}",
    ),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"), _REDACTED),
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), _REDACTED),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), _REDACTED),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), _REDACTED),
    (re.compile(r"AIza[0-9A-Za-z_\-]{20,}"), _REDACTED),
)


def _looks_sensitive_key(key: str) -> bool:
    kl = key.lower()
    return any(token in kl for token in _SENSITIVE_KEY_TOKENS)


def _redact_env_kv(text: str) -> str:
    """Redact ``KEY=VALUE`` and ``KEY="VALUE"`` / ``KEY='VALUE'`` pairs."""

    def repl_quoted(match: re.Match[str]) -> str:
        key = match.group("key")
        quote = match.group("q")
        if _looks_sensitive_key(key):
            return f"{key}={quote}{_REDACTED}{quote}"
        return match.group(0)

    def repl_unquoted(match: re.Match[str]) -> str:
        key = match.group("key")
        if _looks_sensitive_key(key):
            return f"{key}={_REDACTED}"
        return match.group(0)

    # Quoted form first so we do not accidentally match the closing quote as
    # part of the unquoted "value" character class.
    text = re.sub(
        r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<q>['\"])(?P<val>[^'\"]*)(?P=q)",
        repl_quoted,
        text,
    )
    text = re.sub(
        r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<val>[^\s'\"]+)",
        repl_unquoted,
        text,
    )
    return text


def _redact_known_env_values(text: str, extra_values: Iterable[str] = ()) -> str:
    values: set[str] = set()
    for k, v in os.environ.items():
        if v and len(v) >= 8 and _looks_sensitive_key(k):
            values.add(v)
    for extra in extra_values:
        if extra and len(extra) >= 4:
            values.add(extra)
    # Longest first: prevents a prefix from replacing a suffix's content.
    for v in sorted(values, key=len, reverse=True):
        text = text.replace(v, _REDACTED)
    return text


def redact_secrets(text: str, extra_values: Iterable[str] = ()) -> str:
    """Redact obviously sensitive substrings from ``text``.

    Rules applied in order:
      1. Known-shape token patterns (``sk-ant-...``, ``Bearer ...``,
         ``Authorization: Basic ...``, ``ghp_...`` etc.).
      2. ``KEY=VALUE`` pairs whose key name suggests a secret, incl. quoted.
      3. Verbatim values pulled from the current environment for env vars
         whose name suggests a secret, plus any caller-supplied
         ``extra_values`` (fake secrets in tests, config-loaded literals).
    """
    if not text:
        return text
    for pat, replacement in _VALUE_PATTERNS:
        text = pat.sub(replacement, text)
    text = _redact_env_kv(text)
    text = _redact_known_env_values(text, extra_values)
    return text
