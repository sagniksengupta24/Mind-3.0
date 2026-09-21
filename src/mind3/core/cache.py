"""Content-Addressed Verification Cache for Mind 3.0.

Provides deterministic, hash-keyed caching of EDA gate verification results
to prevent redundant, expensive re-execution of formal BMC, coverage simulation,
and physical synthesis across identical code snapshots.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CacheEntry:
    """Represents a cached gate verification outcome."""

    cache_key: str
    gate_name: str
    passed: bool
    result: dict[str, Any]
    timestamp: float


class ContentAddressedCache:
    """Disk-backed, content-addressed cache for EDA verification results."""

    def __init__(self, cache_dir: Path | str) -> None:
        """Initialize cache in the specified directory."""
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._hits: int = 0
        self._misses: int = 0

    @staticmethod
    def hash_sources(sources: list[Path]) -> str:
        """Compute combined SHA-256 digest over source file contents."""
        hasher = hashlib.sha256()
        for src in sorted(sources, key=lambda p: str(p)):
            if src.exists() and src.is_file():
                hasher.update(src.name.encode("utf-8"))
                hasher.update(src.read_bytes())
        return hasher.hexdigest()

    @classmethod
    def compute_key(
        cls,
        sources: list[Path],
        contract_json: str,
        gate_name: str,
        tool_flags: str = "",
    ) -> str:
        """Generate canonical content-addressed key."""
        src_hash = cls.hash_sources(sources)
        payload = f"{src_hash}|{contract_json}|{gate_name}|{tool_flags}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> dict[str, Any] | None:
        """Retrieve cached gate result if present."""
        entry_file = self.cache_dir / f"{cache_key}.json"
        if not entry_file.exists():
            self._misses += 1
            return None
        try:
            data = json.loads(entry_file.read_text(encoding="utf-8"))
            self._hits += 1
            return data.get("result")
        except Exception:
            self._misses += 1
            return None

    def put(self, cache_key: str, gate_name: str, result: dict[str, Any]) -> None:
        """Persist gate result under content-addressed key."""
        entry_file = self.cache_dir / f"{cache_key}.json"
        payload = {
            "cache_key": cache_key,
            "gate_name": gate_name,
            "passed": bool(result.get("passed", False)),
            "result": result,
        }
        entry_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def clear(self) -> int:
        """Purge all cached entries and return count of removed items."""
        count = 0
        for entry_file in self.cache_dir.glob("*.json"):
            entry_file.unlink()
            count += 1
        self._hits = 0
        self._misses = 0
        return count

    @property
    def stats(self) -> dict[str, int]:
        """Return cache performance telemetry."""
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total_entries": len(list(self.cache_dir.glob("*.json"))),
        }
