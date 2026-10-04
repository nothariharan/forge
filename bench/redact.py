"""Keep secrets out of recorded artifacts (command.json, launcher.json).

Environment variables are recorded only from an allowlist of known path/hash settings; any other
FORGE_* variable is listed by name with its value redacted. Free text (commands) is scrubbed of
values that look like credentials.
"""
from __future__ import annotations

import re
from typing import Mapping

REDACTED = "<redacted>"

# FORGE_* settings that hold paths or public hashes, never credentials.
ENV_ALLOWLIST = frozenset({
    "FORGE_TESS_CSV", "FORGE_TESS_SPEC", "FORGE_TESS_SHA256", "FORGE_TESS_PRELOCK_OUT",
    "FORGE_LEDGER_DB", "FORGE_EPISODE_DIR",
})

_SECRET_NAME = r"[A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)[A-Za-z0-9_]*"
_PATTERNS = [
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"), REDACTED),                               # Anthropic / OpenAI keys
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{8,}"), REDACTED),             # GitHub tokens
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}"), REDACTED),
    (re.compile(r"\bxox[abpr]-[A-Za-z0-9\-]{8,}"), REDACTED),                         # Slack
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), REDACTED),                                  # AWS access key id
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"), r"\1" + REDACTED),
    (re.compile(r"(://[^/\s:@]*:)[^@\s/]+@"), r"\1" + REDACTED + "@"),               # user:pass@ in URLs
    (re.compile(rf"(?i)(\b{_SECRET_NAME}\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"), r"\1" + REDACTED),
    (re.compile(r"(?i)(--[A-Za-z0-9_\-]*(?:key|token|secret|password|passwd|credential|auth)[A-Za-z0-9_\-]*[=\s]+)(\S+)"),
     r"\1" + REDACTED),
]


def redact_text(text: str) -> str:
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


def recorded_env(environ: Mapping[str, str]) -> dict[str, str]:
    """FORGE_* settings for the record: allowlisted values kept, everything else redacted."""
    return {k: (redact_text(v) if k in ENV_ALLOWLIST else REDACTED)
            for k, v in sorted(environ.items()) if k.startswith("FORGE_")}
