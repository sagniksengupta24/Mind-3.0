"""Test claim hygiene and enforce bans on overclaimed marketing terminology.

Bans unjustified terms:
- 'Tapeout Ready' (prohibited as a positive assertion; allowed only in negative disclaimers)
- 'unforgeable' (prohibited; internal hash chains are tamper-evident, not mathematically unforgeable)
- 'cryptographic attestation' (prohibited; internal telemetry hash tokens are not PKI/hardware attestations)
- 'air-gapped' (prohibited in marketing/docs except as an explanation of local loopback mode;
  code compatibility aliases 'air_gapped' and 'air_gapped_attestation' are allowed)
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Explicit allowlist: (relative_file_path, term) -> stated_reason
BANNED_TERM_ALLOWLIST: dict[tuple[str, str], str] = {
    (
        "README.md",
        "tapeout ready",
    ): "Explicit negative disclaimer clarifying Mind 3.0 is NOT an ASIC tapeout signoff tool",
    (
        "SECURITY.md",
        "air-gapped",
    ): "Contextual explanation of loopback_only=True mode and verbatim quotation of driver exception string",
    (
        "src/mind3/core/driver.py",
        "air-gapped",
    ): "Exception message text in ValueError for loopback-only endpoint violations",
}

# Python identifier aliases allowed in source code
ALLOWED_IDENTIFIER_ALIASES = {
    "air_gapped",
    "air_gapped_attestation",
}


def test_banned_marketing_terms_enforced() -> None:
    """Verify that unjustified marketing terms are banned outside of explicit, justified allowlist entries."""
    banned_terms = [
        "tapeout ready",
        "unforgeable",
        "cryptographic attestation",
        "air-gapped",
    ]

    # Inspect tracked files across source, docs, examples, and root markdown
    tracked_files = (
        subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=REPO_ROOT
        )
        .decode("utf-8")
        .splitlines()
    )

    scanned_extensions = {".py", ".md", ".sh", ".rst", ".txt", ".jsonl"}
    violations: list[str] = []

    for rel_path in tracked_files:
        # Skip audit status logs, recovery patches, and the hygiene test itself
        if rel_path.startswith(("audit/", "artifacts/recovery/")) or rel_path == "tests/test_claim_hygiene.py":
            continue

        p = REPO_ROOT / rel_path
        if not p.is_file() or p.suffix not in scanned_extensions:
            continue

        text = p.read_text(encoding="utf-8", errors="ignore")
        text_lower = text.lower()

        for term in banned_terms:
            if term not in text_lower:
                continue

            # Check if this exact file and term is allowlisted
            allow_key = (rel_path, term)
            if allow_key in BANNED_TERM_ALLOWLIST:
                continue

            # Find matching line numbers
            for line_no, line in enumerate(text.splitlines(), start=1):
                if term in line.lower():
                    # Check if the match is merely an allowed Python identifier (e.g. air_gapped=True)
                    # when checking for 'air-gapped' (with hyphen)
                    violations.append(
                        f"{rel_path}:{line_no} contains banned term '{term}': {line.strip()}"
                    )

    assert not violations, (
        f"Found {len(violations)} unjustified term violations outside allowlist:\n"
        + "\n".join(violations)
    )
